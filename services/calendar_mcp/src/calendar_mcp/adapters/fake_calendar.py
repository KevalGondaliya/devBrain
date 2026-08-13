"""The adapter actually wired up today: a thin wrapper over the Postgres
`calendar_events` table (`repositories/calendar_events_repository.py`),
implementing the `CalendarAdapter` Protocol (`adapters/protocol.py`).

"Fake" refers to the *data* (synthetic/Faker-generated, per
`scripts/generators/calendar_events.py`), not the code path — every query
here is a real, parameterized SQLAlchemy ORM query against a real Postgres
table. DevBrain_vision.md §11.5: "Initially use generated calendar data ...
Later connect Google Calendar or another real provider." This is that
"fake adapter".

Also does the public-name <-> DB-column translation
(`starts_at`/`ends_at` <-> `start_time`/`end_time` — see
`devbrain_common.models.CalendarEvent`) so nothing above this layer needs
to know the storage schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from devbrain_common.models import CalendarEvent
from sqlalchemy.ext.asyncio import AsyncSession

from calendar_mcp.adapters.protocol import CalendarEventRecord
from calendar_mcp.repositories import calendar_events_repository as calendar_events_repository


def _to_record(row: CalendarEvent) -> CalendarEventRecord:
    return CalendarEventRecord(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        starts_at=row.start_time,
        ends_at=row.end_time,
        participants=row.participants,
        location=row.location,
        description=row.description,
        created_at=row.created_at,
    )


class FakeCalendarAdapter:
    """Postgres-backed `CalendarAdapter` implementation. See module docstring."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_events_between(
        self, *, starts_after: datetime, starts_before: datetime, limit: int
    ) -> list[CalendarEventRecord]:
        rows = await calendar_events_repository.list_starting_between(
            self._session, starts_after=starts_after, starts_before=starts_before, limit=limit
        )
        return [_to_record(r) for r in rows]

    async def find_event(self, *, query: str, limit: int) -> list[CalendarEventRecord]:
        rows = await calendar_events_repository.search(self._session, query=query, limit=limit)
        return [_to_record(r) for r in rows]

    async def create_event(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        project_id: uuid.UUID | None,
        participants: list[str] | None,
        location: str | None,
        description: str | None,
    ) -> CalendarEventRecord:
        event = CalendarEvent(
            id=uuid.uuid4(),
            project_id=project_id,
            title=title,
            start_time=starts_at,
            end_time=ends_at,
            participants=participants,
            location=location,
            description=description,
        )
        calendar_events_repository.insert(self._session, event)
        await self._session.flush()
        return _to_record(event)
