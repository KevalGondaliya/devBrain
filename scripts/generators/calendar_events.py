"""Calendar event generation (DevBrain_vision.md §13 step 8)."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta

from devbrain_common.models import CalendarEvent, Meeting, Project
from faker import Faker

from .common import random_datetime_between, utcnow
from .people import Person

EVENT_TITLES = (
    "1:1",
    "Sprint Planning",
    "Design Review",
    "All Hands",
    "Interview",
    "Customer Call",
    "Vendor Call",
    "Focus Block",
    "Team Lunch",
    "Retro",
)

LOCATIONS = ("Zoom", "Google Meet", "Conference Room A", "Conference Room B", None)


@dataclass
class CalendarEventsResult:
    events: list[CalendarEvent]


def generate_calendar_events(
    fake: Faker,
    rng: random.Random,
    projects: list[Project],
    meetings: list[Meeting],
    people: list[Person],
    count: int,
) -> CalendarEventsResult:
    now = utcnow()
    earliest = now - timedelta(days=400)
    events: list[CalendarEvent] = []

    # Tie roughly a third of calendar events 1:1 to an existing meeting.
    meeting_linked = min(count // 3, len(meetings))
    linked_meetings = rng.sample(meetings, k=meeting_linked) if meeting_linked else []
    for meeting in linked_meetings:
        end = meeting.date + timedelta(minutes=meeting.duration_minutes or 30)
        events.append(
            CalendarEvent(
                id=uuid.uuid4(),
                project_id=meeting.project_id,
                title=meeting.title,
                start_time=meeting.date,
                end_time=end,
                participants=meeting.participants,
                location=rng.choice(LOCATIONS),
                description=f"Calendar entry for meeting '{meeting.title}'.",
                created_at=meeting.date - timedelta(days=rng.randint(1, 5)),
            )
        )

    for _ in range(count - len(events)):
        project = rng.choice(projects) if projects and rng.random() < 0.5 else None
        start = random_datetime_between(rng, earliest, now + timedelta(days=60))
        duration = rng.choice([15, 30, 30, 45, 60])
        participants: list[str] = []
        if people:
            k = rng.randint(1, min(4, len(people)))
            participants = [p.name for p in rng.sample(people, k)]
        events.append(
            CalendarEvent(
                id=uuid.uuid4(),
                project_id=project.id if project else None,
                title=rng.choice(EVENT_TITLES),
                start_time=start,
                end_time=start + timedelta(minutes=duration),
                participants=participants,
                location=rng.choice(LOCATIONS),
                description=fake.sentence() if rng.random() < 0.6 else None,
                created_at=start - timedelta(days=rng.randint(1, 10)),
            )
        )
    return CalendarEventsResult(events=events)
