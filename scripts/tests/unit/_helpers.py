"""Shared fixture-building helper for Phase 2 generator unit tests.

Builds the same dependency chain as `scripts/generate_all.py`'s `_run`,
deterministically and without touching a database, so every unit test in
this directory can assert messiness invariants against one consistent
in-memory dataset.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from faker import Faker

import generate_all
from generators.decisions import DecisionsResult, generate_decisions
from generators.meetings import MeetingsResult, generate_meetings
from generators.notes import NotesResult, generate_notes
from generators.people import Person, generate_people
from generators.projects import ProjectsResult, generate_projects
from generators.tasks import TasksResult, generate_tasks


@dataclass
class World:
    fake: Faker
    rng: random.Random
    people: list[Person]
    projects: ProjectsResult
    meetings: MeetingsResult
    decisions: DecisionsResult
    tasks: TasksResult
    notes: NotesResult


def build_world(seed: int = 42, size: str = "small") -> World:
    random.seed(seed)
    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)

    cfg = generate_all.SIZE_CONFIGS[size]
    people = generate_people(fake, rng)
    projects = generate_projects(fake, rng, people, cfg["projects"])
    meetings = generate_meetings(
        fake, rng, projects.projects, people, projects.renamed, cfg["meetings"]
    )
    decisions = generate_decisions(
        fake, rng, projects.projects, meetings.meetings, cfg["decisions"]
    )
    tasks = generate_tasks(fake, rng, projects.projects, decisions.decisions, people, cfg["tasks"])
    notes = generate_notes(
        fake,
        rng,
        projects.projects,
        people,
        meetings.meetings,
        decisions.decisions,
        projects.renamed,
        cfg["notes"],
    )
    return World(
        fake=fake,
        rng=rng,
        people=people,
        projects=projects,
        meetings=meetings,
        decisions=decisions,
        tasks=tasks,
        notes=notes,
    )
