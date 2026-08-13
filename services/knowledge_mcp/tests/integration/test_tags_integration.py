"""Tag rename cascades to every `note_tags` row, against real seeded data."""

from __future__ import annotations

import pytest
from devbrain_common.auth import Role
from knowledge_mcp.services import tags_service

pytestmark = pytest.mark.usefixtures("patched_uow")


async def test_rename_hot_tag_preserves_note_count() -> None:
    # "mcp" is one of Phase 2's fixed HOT_TAGS, guaranteed to be used by
    # multiple notes in any seed size (scripts/generators/notes.py).
    before = await tags_service.list_tags()
    mcp_before = next(t for t in before if t.name == "mcp")
    assert mcp_before.note_count > 0

    renamed = await tags_service.rename_tag(
        old_name="mcp", new_name="model-context-protocol", actor="integration-test", role=Role.ADMIN
    )
    assert renamed.name == "model-context-protocol"
    assert renamed.note_count == mcp_before.note_count

    after = await tags_service.list_tags()
    names = {t.name for t in after}
    assert "mcp" not in names
    assert "model-context-protocol" in names


async def test_rename_into_existing_tag_merges_note_counts() -> None:
    before = await tags_service.list_tags()
    postgres_count = next(t.note_count for t in before if t.name == "postgres")
    python_count = next(t.note_count for t in before if t.name == "python")

    merged = await tags_service.rename_tag(
        old_name="postgres", new_name="python", actor="integration-test", role=Role.ADMIN
    )
    assert merged.name == "python"
    # Merged count is at most the sum (fewer if some notes already had both
    # tags, since a note can't carry the same tag twice).
    assert merged.note_count <= postgres_count + python_count
    assert merged.note_count >= python_count

    after = await tags_service.list_tags()
    assert "postgres" not in {t.name for t in after}
