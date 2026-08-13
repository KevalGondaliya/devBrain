"""Project generation — the root of the dependency chain (DevBrain_vision.md §13)."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta

from devbrain_common.models import Project
from faker import Faker

from .common import utcnow
from .people import Person

STATUSES = ("planned", "active", "blocked", "completed", "archived")
STATUS_WEIGHTS = (0.15, 0.4, 0.15, 0.2, 0.1)
PRIORITIES = ("low", "medium", "high", "critical")
PRIORITY_WEIGHTS = (0.2, 0.4, 0.3, 0.1)

ADJECTIVES = (
    "Command",
    "Nexus",
    "Forge",
    "Pilot",
    "Atlas",
    "Signal",
    "Beacon",
    "Origin",
    "Relay",
    "Vector",
    "Horizon",
    "Cascade",
)
NOUNS = (
    "Center",
    "Platform",
    "Hub",
    "Engine",
    "Console",
    "Gateway",
    "Suite",
    "Workbench",
    "Portal",
    "Sync",
    "Pipeline",
    "Dashboard",
)


@dataclass
class ProjectsResult:
    projects: list[Project]
    # project id -> its old (pre-rename) name. At most one entry today, but
    # kept as a dict so a future run could inject more than one renamed
    # project without changing the return shape.
    renamed: dict[uuid.UUID, str]


def _project_name(fake: Faker, rng: random.Random, used: set[str]) -> str:
    for _ in range(50):
        name = f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)}"
        if name not in used:
            used.add(name)
            return name
    # Astronomically unlikely fallback once the adjective/noun grid is exhausted.
    name = f"{fake.word().title()} Initiative {len(used) + 1}"
    used.add(name)
    return name


def generate_projects(
    fake: Faker, rng: random.Random, people: list[Person], count: int
) -> ProjectsResult:
    """Generate `count` projects plus one deliberately-renamed project.

    The renamed project's *current* `Project.name` is a fresh name; its old
    name is returned via `ProjectsResult.renamed` so `generate_meetings` /
    `generate_notes` can reference the old name in an older meeting/note's
    text — the "renamed project" messiness invariant from
    DevBrain_vision.md §16.
    """
    now = utcnow()
    used_names: set[str] = set()
    projects: list[Project] = []
    for _ in range(count):
        name = _project_name(fake, rng, used_names)
        status = rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
        start = now - timedelta(days=rng.randint(30, 720))
        target = start + timedelta(days=rng.randint(60, 400))
        owner = rng.choice(people).name if people else None
        project = Project(
            id=uuid.uuid4(),
            name=name,
            description=fake.paragraph(nb_sentences=3),
            status=status,
            priority=rng.choices(PRIORITIES, weights=PRIORITY_WEIGHTS, k=1)[0],
            start_date=start,
            target_date=target,
            owner=owner,
        )
        projects.append(project)

    renamed: dict[uuid.UUID, str] = {}
    if projects:
        renamed_project = rng.choice(projects)
        old_name = _project_name(fake, rng, used_names)
        renamed[renamed_project.id] = old_name

    return ProjectsResult(projects=projects, renamed=renamed)
