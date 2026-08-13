"""Meeting generation (DevBrain_vision.md §13 step 3)."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from devbrain_common.models import Meeting, Project
from faker import Faker

from .common import random_datetime_between, utcnow
from .people import Person

MEETING_TOPICS = (
    "Architecture Review",
    "Sprint Planning",
    "Retro",
    "Design Sync",
    "Standup Recap",
    "Roadmap Planning",
    "Security Review",
    "Incident Postmortem",
    "Onboarding Sync",
    "1:1",
    "Vendor Evaluation",
    "Database Migration Planning",
    "API Design Review",
    "Auth Review",
    "Performance Review",
)

AGENDA_ITEMS = (
    "MCP server boundaries",
    "the authentication approach",
    "database architecture",
    "the release timeline",
    "the on-call rotation",
    "test coverage gaps",
    "third-party API rate limits",
    "the onboarding checklist",
    "budget approval",
    "the rollout plan",
)


@dataclass
class MeetingsResult:
    meetings: list[Meeting]


def _participants(rng: random.Random, people: list[Person]) -> list[str]:
    if not people:
        return []
    k = rng.randint(2, min(6, len(people)))
    return [p.name for p in rng.sample(people, k)]


def _build_meeting(
    fake: Faker,
    rng: random.Random,
    project: Project | None,
    people: list[Person],
    date: datetime,
    *,
    title_override: str | None = None,
    summary_override: str | None = None,
) -> Meeting:
    title = title_override or (
        f"{rng.choice(MEETING_TOPICS)}" + (f" — {project.name}" if project else "")
    )
    summary = summary_override or (
        f"Discussed {rng.choice(AGENDA_ITEMS)} and {rng.choice(AGENDA_ITEMS)}. "
        f"{fake.sentence()} {fake.sentence()}"
    )
    return Meeting(
        id=uuid.uuid4(),
        project_id=project.id if project else None,
        title=title,
        date=date,
        duration_minutes=rng.choice([15, 30, 30, 45, 60, 60, 90]),
        participants=_participants(rng, people),
        summary=summary,
        transcript_path=(
            None
            if rng.random() < 0.3
            else f"transcripts/{date.date().isoformat()}-{rng.randint(1000, 9999)}.txt"
        ),
    )


def generate_meetings(
    fake: Faker,
    rng: random.Random,
    projects: list[Project],
    people: list[Person],
    renamed: dict[uuid.UUID, str],
    count: int,
) -> MeetingsResult:
    """Generate `count` meetings, weighted so a handful of projects dominate
    meeting volume (organic, not uniform), plus one forced meeting for the
    renamed project (see `generate_projects`) whose title/summary still
    references the *old* project name — the "renamed project" messiness
    invariant from DevBrain_vision.md §16.
    """
    now = utcnow()
    earliest = now - timedelta(days=730)
    meetings: list[Meeting] = []

    remaining = count
    if renamed and remaining > 0 and projects:
        project_id, old_name = next(iter(renamed.items()))
        renamed_project: Project = next((p for p in projects if p.id == project_id), projects[0])
        old_date = earliest + timedelta(days=rng.randint(0, 30))
        meetings.append(
            _build_meeting(
                fake,
                rng,
                renamed_project,
                people,
                old_date,
                title_override=f"Kickoff — {old_name}",
                summary_override=(
                    f"Kickoff meeting for {old_name} (this project was later renamed to "
                    f"'{renamed_project.name}'). {fake.sentence()}"
                ),
            )
        )
        remaining -= 1

    weights = [rng.random() ** 2 + 0.05 for _ in projects] if projects else []
    for _ in range(remaining):
        meeting_project: Project | None = (
            rng.choices(projects, weights=weights, k=1)[0]
            if projects and rng.random() < 0.9
            else None
        )
        date = random_datetime_between(rng, earliest, now)
        meetings.append(_build_meeting(fake, rng, meeting_project, people, date))

    return MeetingsResult(meetings=meetings)
