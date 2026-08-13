#!/usr/bin/env python
"""Populate the DevBrain Postgres schema with reproducible synthetic data.

Must be run via the venv's `python` directly (this checkout's path has a
colon in it, which breaks `uv run` — see PROGRESS_REPORT.md Phase 1 "Local
environment quirk" and Phase 2's own notes):

    .venv/bin/python scripts/generate_all.py --size small
    .venv/bin/python scripts/generate_all.py --size default --truncate
    .venv/bin/python scripts/generate_all.py --size large --truncate

Dependency order (DevBrain_vision.md §13):
    projects -> people (in-memory only, no `people` table) -> meetings ->
    decisions -> tasks -> notes (+ tags/note_tags/links) -> embeddings ->
    github_activities -> calendar_events

Reproducibility: both the stdlib `random` module (per the task spec) and a
dedicated `random.Random` instance threaded through every generator are
seeded from `--seed` / `SEED_RANDOM_SEED` (default 42); Faker is seeded the
same way via `fake.seed_instance`. Re-running with the same seed and size
regenerates identical data (embeddings included, since the embedding model
is deterministic given the same input text).
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from pathlib import Path

from faker import Faker
from sqlalchemy import delete

# Make the sibling `generators` package (and `embeddings`) importable when
# this file is executed directly as `python scripts/generate_all.py`, since
# in that mode only this file's own directory is on `sys.path`, not the repo
# root or an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from devbrain_common.config import get_settings  # noqa: E402
from devbrain_common.db import session_scope  # noqa: E402
from devbrain_common.models import (  # noqa: E402
    CalendarEvent,
    Decision,
    Embedding,
    GithubActivity,
    Link,
    Meeting,
    Note,
    NoteTag,
    Project,
    Tag,
    Task,
)

from embeddings import compute_note_embeddings  # noqa: E402
from generators.calendar_events import generate_calendar_events  # noqa: E402
from generators.decisions import generate_decisions  # noqa: E402
from generators.github_activity import generate_github_activities  # noqa: E402
from generators.meetings import generate_meetings  # noqa: E402
from generators.notes import generate_notes  # noqa: E402
from generators.people import generate_people  # noqa: E402
from generators.projects import generate_projects  # noqa: E402
from generators.tasks import generate_tasks  # noqa: E402

SIZE_CONFIGS: dict[str, dict[str, int]] = {
    # ~10% of "default", per DevBrain_vision.md §12 — used by CI/QA for fast
    # iteration (see ORCHESTRATION.md §5's QA loop).
    "small": {
        "projects": 2,
        "meetings": 20,
        "decisions": 50,
        "tasks": 100,
        "notes": 100,
        "github_activities": 200,
        "calendar_events": 50,
    },
    # DevBrain_vision.md §12's initial target, verbatim.
    "default": {
        "projects": 20,
        "meetings": 200,
        "decisions": 500,
        "tasks": 1000,
        "notes": 1000,
        "github_activities": 2000,
        "calendar_events": 500,
    },
    # DevBrain_vision.md §12's "Later" target gives projects/meetings/tasks/
    # notes explicitly (100 / 5,000 / 20,000 / 50,000). It does not give a
    # number for decisions/github_activities/calendar_events at this tier,
    # so this script picks:
    #   - decisions: hold the *default* tier's decisions-per-meeting ratio
    #     constant (500/200 = 2.5x) and apply it to 5,000 meetings -> 12,500.
    #   - github_activities / calendar_events: scaled 5x, matching the
    #     *projects* multiplier (20 -> 100), not the more aggressive
    #     tasks/notes multipliers (20x / 50x) — GitHub and calendar cadence
    #     realistically tracks project count and meeting cadence, not
    #     task/note volume. 2,000*5=10,000, 500*5=2,500.
    "large": {
        "projects": 100,
        "meetings": 5000,
        "decisions": 12500,
        "tasks": 20000,
        "notes": 50000,
        "github_activities": 10000,
        "calendar_events": 2500,
    },
}

# Delete order respects FK dependencies (children before parents).
# Deliberately never includes `audit_logs` or `approvals` — those are real
# system output / Phase 6 governance data, not seed data this script owns.
_TRUNCATE_ORDER = (
    Embedding,
    Link,
    NoteTag,
    Note,
    Tag,
    CalendarEvent,
    GithubActivity,
    Task,
    Decision,
    Meeting,
    Project,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--size",
        choices=sorted(SIZE_CONFIGS),
        default=None,
        help="Dataset size (default: SEED_DATASET_SIZE env var, itself defaulting to 'default').",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Override SEED_RANDOM_SEED for this run."
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete existing seeded rows first (never touches audit_logs/approvals).",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL for this run (e.g. to target db_test).",
    )
    return parser.parse_args(argv)


async def _truncate(database_url: str | None) -> None:
    async with session_scope(database_url) as session:
        for model in _TRUNCATE_ORDER:
            await session.execute(delete(model))


async def _run(size: str, seed: int, truncate: bool, database_url: str | None) -> dict[str, int]:
    random.seed(seed)
    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)

    if truncate:
        print("Truncating existing seed data...")
        await _truncate(database_url)

    cfg = SIZE_CONFIGS[size]

    people = generate_people(fake, rng)

    t0 = time.monotonic()
    projects_result = generate_projects(fake, rng, people, cfg["projects"])
    meetings_result = generate_meetings(
        fake, rng, projects_result.projects, people, projects_result.renamed, cfg["meetings"]
    )
    decisions_result = generate_decisions(
        fake, rng, projects_result.projects, meetings_result.meetings, cfg["decisions"]
    )
    tasks_result = generate_tasks(
        fake, rng, projects_result.projects, decisions_result.decisions, people, cfg["tasks"]
    )
    notes_result = generate_notes(
        fake,
        rng,
        projects_result.projects,
        people,
        meetings_result.meetings,
        decisions_result.decisions,
        projects_result.renamed,
        cfg["notes"],
    )
    github_result = generate_github_activities(
        fake, rng, projects_result.projects, tasks_result.tasks, people, cfg["github_activities"]
    )
    calendar_result = generate_calendar_events(
        fake,
        rng,
        projects_result.projects,
        meetings_result.meetings,
        people,
        cfg["calendar_events"],
    )
    print(f"Generated in-memory rows in {time.monotonic() - t0:.1f}s.")

    settings = get_settings()
    print(
        f"Computing embeddings for {len(notes_result.notes)} notes ({settings.embedding_model})..."
    )
    t0 = time.monotonic()
    embeddings = compute_note_embeddings(notes_result.notes, model_name=settings.embedding_model)
    print(f"Embeddings computed in {time.monotonic() - t0:.1f}s.")

    async with session_scope(database_url) as session:
        session.add_all(projects_result.projects)
        await session.flush()
        session.add_all(meetings_result.meetings)
        await session.flush()
        session.add_all(decisions_result.decisions)
        await session.flush()
        session.add_all(tasks_result.tasks)
        await session.flush()
        session.add_all(notes_result.tags)
        session.add_all(notes_result.notes)
        await session.flush()
        session.add_all(notes_result.note_tags)
        session.add_all(notes_result.links)
        session.add_all(embeddings)
        await session.flush()
        session.add_all(github_result.activities)
        session.add_all(calendar_result.events)
        await session.flush()

    return {
        "projects": len(projects_result.projects),
        "meetings": len(meetings_result.meetings),
        "decisions": len(decisions_result.decisions),
        "tasks": len(tasks_result.tasks),
        "notes": len(notes_result.notes),
        "tags": len(notes_result.tags),
        "note_tags": len(notes_result.note_tags),
        "links": len(notes_result.links),
        "embeddings": len(embeddings),
        "github_activities": len(github_result.activities),
        "calendar_events": len(calendar_result.events),
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    size = args.size or settings.seed_dataset_size
    seed = args.seed if args.seed is not None else settings.seed_random_seed

    print(f"Seeding DevBrain data: size={size} seed={seed} truncate={args.truncate}")
    counts = asyncio.run(_run(size, seed, args.truncate, args.database_url))
    print("Done. Row counts:")
    for name, n in counts.items():
        print(f"  {name}: {n}")


if __name__ == "__main__":
    main()
