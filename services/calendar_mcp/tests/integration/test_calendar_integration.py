"""Real `db_test` round-trips.

Seeded calendar events (Phase 2's `--size small --seed 42`) span a wide,
random date range (see `scripts/generators/calendar_events.py`), so
`get_today_events`/`get_week_events` are exercised deterministically by
creating real events at known offsets from "now" via `create_event` itself,
rather than depending on the random seed happening to place an event in
today's window. `find_event` is exercised against the real seeded data
directly, since keyword search doesn't depend on timing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from calendar_mcp.services import calendar_service
from devbrain_common.approvals import decide_approval, request_approval
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, NotFoundError
from devbrain_common.models import CalendarEvent, Project
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def _a_real_project_id(db_session: AsyncSession) -> str:
    result = await db_session.execute(select(Project.id).limit(1))
    return str(result.scalar_one())


async def _a_real_event(db_session: AsyncSession) -> CalendarEvent:
    result = await db_session.execute(select(CalendarEvent).limit(1))
    return result.scalars().one()


async def test_find_event_finds_a_real_seeded_event(patched_uow: AsyncSession) -> None:
    event = await _a_real_event(patched_uow)
    fragment = event.title.split()[0]

    results = await calendar_service.find_event(query=fragment)
    assert any(r.id == str(event.id) for r in results)


async def test_create_event_appears_in_get_today_events(patched_uow: AsyncSession) -> None:
    now = datetime.now(UTC)
    starts_at = now.replace(hour=12, minute=0, second=0, microsecond=0)
    if starts_at <= now:
        starts_at = now + timedelta(hours=1)
    ends_at = starts_at + timedelta(minutes=30)

    created = await calendar_service.create_event(
        title="Integration-created today event",
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
        actor="tester",
        role=Role.ADMIN,
    )

    todays = await calendar_service.get_today_events()
    assert any(e.id == created.id for e in todays)


async def test_create_event_far_future_not_in_today_or_week(patched_uow: AsyncSession) -> None:
    starts_at = datetime.now(UTC) + timedelta(days=30)
    ends_at = starts_at + timedelta(minutes=30)

    created = await calendar_service.create_event(
        title="Integration-created far-future event",
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
        actor="tester",
        role=Role.ADMIN,
    )

    todays = await calendar_service.get_today_events()
    week = await calendar_service.get_week_events()
    assert all(e.id != created.id for e in todays)
    assert all(e.id != created.id for e in week)


async def test_create_event_within_week_appears_in_get_week_events(
    patched_uow: AsyncSession,
) -> None:
    starts_at = datetime.now(UTC) + timedelta(days=3)
    ends_at = starts_at + timedelta(minutes=30)

    created = await calendar_service.create_event(
        title="Integration-created this-week event",
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
        actor="tester",
        role=Role.ADMIN,
    )

    week = await calendar_service.get_week_events()
    assert any(e.id == created.id for e in week)


async def test_create_event_persists_against_real_project(patched_uow: AsyncSession) -> None:
    project_id = await _a_real_project_id(patched_uow)
    starts_at = datetime.now(UTC) + timedelta(days=1)
    ends_at = starts_at + timedelta(hours=1)

    created = await calendar_service.create_event(
        title="Integration-created project event",
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
        project_id=project_id,
        participants=["Ada Lovelace"],
        location="Zoom",
        actor="tester",
        role=Role.ADMIN,
    )
    assert created.project_id == project_id
    assert created.participants == ["Ada Lovelace"]


async def test_create_event_unknown_project_raises_not_found(patched_uow: AsyncSession) -> None:
    starts_at = datetime.now(UTC) + timedelta(days=1)
    ends_at = starts_at + timedelta(hours=1)

    with pytest.raises(NotFoundError):
        await calendar_service.create_event(
            title="Orphan event",
            starts_at=starts_at.isoformat(),
            ends_at=ends_at.isoformat(),
            project_id=str(uuid.uuid4()),
            actor="tester",
            role=Role.ADMIN,
        )


async def test_create_event_idempotency_key_prevents_duplicate(patched_uow: AsyncSession) -> None:
    starts_at = datetime.now(UTC) + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=45)
    key = f"integration-test-{uuid.uuid4()}"
    title = "Idempotent integration event"

    first = await calendar_service.create_event(
        title=title,
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
        idempotency_key=key,
        actor="tester",
        role=Role.ADMIN,
    )
    second = await calendar_service.create_event(
        title=title,
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
        idempotency_key=key,
        actor="tester",
        role=Role.ADMIN,
    )

    assert first.id == second.id

    count_result = await patched_uow.execute(
        select(func.count()).select_from(CalendarEvent).where(CalendarEvent.title == title)
    )
    assert count_result.scalar_one() == 1


async def test_create_event_user_role_requires_approval_end_to_end(
    patched_uow: AsyncSession,
) -> None:
    """Phase 6 human-in-the-loop gate, full round trip against real
    Postgres: a `Role.USER` call without `approval_id` is rejected; after
    `request_approval` + admin `decide_approval`, retrying with that
    `approval_id` succeeds; retrying a third time with the same id fails
    (already consumed)."""
    starts_at = datetime.now(UTC) + timedelta(days=3)
    ends_at = starts_at + timedelta(minutes=30)
    title = "Needs sign-off event"
    call_arguments = {
        "title": title,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "project_id": None,
        "participants": None,
        "location": None,
        "description": None,
    }

    with pytest.raises(ApprovalRequiredError):
        await calendar_service.create_event(
            title=title,
            starts_at=starts_at.isoformat(),
            ends_at=ends_at.isoformat(),
            actor="user-bob",
            role=Role.USER,
        )

    approval = await request_approval(
        patched_uow, actor="user-bob", tool_name="create_event", arguments=call_arguments
    )
    await decide_approval(
        patched_uow, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    created = await calendar_service.create_event(
        title=title,
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
        actor="user-bob",
        role=Role.USER,
        approval_id=str(approval.id),
    )
    assert created.title == title

    with pytest.raises(ApprovalRequiredError):
        await calendar_service.create_event(
            title=title,
            starts_at=starts_at.isoformat(),
            ends_at=ends_at.isoformat(),
            actor="user-bob",
            role=Role.USER,
            approval_id=str(approval.id),
        )
