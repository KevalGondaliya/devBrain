"""Integration test: seed `--size small` against `db_test` and check that row
counts roughly match expectations and FK integrity holds (no orphaned rows).

Requires: `docker compose --profile test up -d db_test` (see ORCHESTRATION.md
§2 / PROGRESS_REPORT.md Phase 1).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from devbrain_common import models
from devbrain_common.db import dispose_engine, session_scope
from sqlalchemy import func, select

import generate_all

from .conftest import TEST_DATABASE_URL


@pytest_asyncio.fixture(autouse=True)
async def _clean_slate() -> AsyncGenerator[None, None]:
    """Leave `db_test` empty of seed rows before and after this test."""
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001 - test-only access
    yield
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001
    await dispose_engine()


async def test_seed_small_row_counts_and_fk_integrity() -> None:
    counts = await generate_all._run(  # noqa: SLF001 - test-only access to the runner
        size="small", seed=42, truncate=False, database_url=TEST_DATABASE_URL
    )

    expected = generate_all.SIZE_CONFIGS["small"]
    entity_keys = (
        "projects",
        "meetings",
        "decisions",
        "tasks",
        "notes",
        "github_activities",
        "calendar_events",
    )
    for key in entity_keys:
        assert counts[key] == expected[key], f"{key}: {counts[key]} != {expected[key]}"
    assert counts["embeddings"] == counts["notes"]
    assert counts["tags"] >= 1
    assert counts["note_tags"] >= counts["notes"]

    async with session_scope(TEST_DATABASE_URL) as session:
        # DB-side counts must match what the generator reported.
        for model, key in (
            (models.Project, "projects"),
            (models.Meeting, "meetings"),
            (models.Decision, "decisions"),
            (models.Task, "tasks"),
            (models.Note, "notes"),
            (models.Tag, "tags"),
            (models.NoteTag, "note_tags"),
            (models.Link, "links"),
            (models.Embedding, "embeddings"),
            (models.GithubActivity, "github_activities"),
            (models.CalendarEvent, "calendar_events"),
        ):
            result = await session.execute(select(func.count()).select_from(model))
            table_name = model.__tablename__
            assert result.scalar_one() == counts[key], f"DB count for {table_name} mismatch"

        # FK integrity spot checks: a real FK constraint makes an orphan
        # impossible to insert, but this proves the generator produced (and
        # the DB accepted) real, resolvable references rather than nulling
        # everything out.
        orphan_tasks = await session.execute(
            select(func.count())
            .select_from(models.Task)
            .outerjoin(models.Project, models.Task.project_id == models.Project.id)
            .where(models.Project.id.is_(None))
        )
        assert orphan_tasks.scalar_one() == 0

        orphan_embeddings = await session.execute(
            select(func.count())
            .select_from(models.Embedding)
            .outerjoin(models.Note, models.Embedding.note_id == models.Note.id)
            .where(models.Note.id.is_(None))
        )
        assert orphan_embeddings.scalar_one() == 0

        orphan_note_tags = await session.execute(
            select(func.count())
            .select_from(models.NoteTag)
            .outerjoin(models.Note, models.NoteTag.note_id == models.Note.id)
            .outerjoin(models.Tag, models.NoteTag.tag_id == models.Tag.id)
            .where((models.Note.id.is_(None)) | (models.Tag.id.is_(None)))
        )
        assert orphan_note_tags.scalar_one() == 0

        # embedding dimensionality matches the schema's Vector(384) column.
        vec_len = await session.execute(select(func.vector_dims(models.Embedding.vector)).limit(1))
        assert vec_len.scalar_one() == models.EMBEDDING_DIM

        # the prompt-injection fixture note landed and is queryable by its
        # documented lookup key.
        fixture = await session.execute(
            select(models.Note).where(models.Note.slug == "prompt-injection-fixture-01")
        )
        assert fixture.scalar_one_or_none() is not None
