"""In-memory pool of synthetic people, shared across every downstream generator.

There is no `people` table in the Phase 1 schema (see
`devbrain_common/models.py`'s module docstring) — person names show up as
free-text fields (`projects.owner`, `tasks.assignee`, `meetings.participants`,
`github_activities.author`, `calendar_events.participants`). This module
exists so the *same* fabricated people recur across those entities (a
believable small team, not a fresh random name every time), which is the
"People" step in DevBrain_vision.md §13's dependency chain.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from faker import Faker

ROLES = (
    "engineer",
    "senior engineer",
    "staff engineer",
    "engineering manager",
    "product manager",
    "designer",
    "founder/CTO",
    "QA engineer",
)

DEFAULT_TEAM_SIZE = 24


@dataclass(frozen=True)
class Person:
    name: str
    email: str
    role: str


def generate_people(
    fake: Faker, rng: random.Random, count: int = DEFAULT_TEAM_SIZE
) -> list[Person]:
    """Generate a reusable pool of `count` distinct people."""
    people: list[Person] = []
    seen_names: set[str] = set()
    attempts = 0
    max_attempts = count * 20
    while len(people) < count and attempts < max_attempts:
        attempts += 1
        name = fake.name()
        if name in seen_names:
            continue
        seen_names.add(name)
        email = f"{name.lower().replace(' ', '.').replace(chr(39), '')}@example.dev"
        role = rng.choice(ROLES)
        people.append(Person(name=name, email=email, role=role))
    return people
