"""`calendar_events` queries: no business logic, no date-range/idempotency
semantics — see `adapters/fake_calendar.py` (the caller) and
`services/calendar_service.py`.

Only ever used by `FakeCalendarAdapter` — this module is deliberately the
*only* place in this service that imports SQLAlchemy/`devbrain_common.models`
for calendar events, so a future `RealCalendarAdapter` swap touches nothing
here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from devbrain_common.models import CalendarEvent
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def _base_query() -> Select[tuple[CalendarEvent]]:
    return select(CalendarEvent).execution_options(populate_existing=True)


async def get_by_id(session: AsyncSession, event_id: uuid.UUID) -> CalendarEvent | None:
    stmt = _base_query().where(CalendarEvent.id == event_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_starting_between(
    session: AsyncSession, *, starts_after: datetime, starts_before: datetime, limit: int
) -> list[CalendarEvent]:
    """Events whose `start_time` falls in `[starts_after, starts_before)`."""
    stmt = (
        _base_query()
        .where(
            CalendarEvent.start_time >= starts_after,
            CalendarEvent.start_time < starts_before,
        )
        .order_by(CalendarEvent.start_time.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def search(session: AsyncSession, *, query: str, limit: int) -> list[CalendarEvent]:
    """`ILIKE` match on title/description/location."""
    pattern = f"%{query}%"
    stmt = (
        _base_query()
        .where(
            or_(
                CalendarEvent.title.ilike(pattern),
                CalendarEvent.description.ilike(pattern),
                CalendarEvent.location.ilike(pattern),
            )
        )
        .order_by(CalendarEvent.start_time.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def insert(session: AsyncSession, event: CalendarEvent) -> None:
    session.add(event)
