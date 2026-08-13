"""Calendar business logic: today/week events, find, create, per
`DevBrain_vision.md` §11.5.

Depends only on the `CalendarAdapter` Protocol (`adapters/protocol.py`),
never on `FakeCalendarAdapter`/`RealCalendarAdapter` directly, for the four
public tool operations (today/week/find/create) — `get_adapter()` below is
the single factory function that decides which concrete adapter backs a
call. Swapping fake -> real (DevBrain_vision.md §24) means changing that one
function; nothing else in this module (or `tools/calendar_tools.py`) needs
to change. Unit tests exploit this directly: they monkeypatch `get_adapter`
to return a hand-written double that implements the Protocol but is neither
`FakeCalendarAdapter` nor `RealCalendarAdapter`, proving this module only
ever calls through the Protocol's methods for those four operations.

The one deliberate exception: `create_event`'s idempotent-replay lookup
(`devbrain_common.idempotency`, shared with `task_mcp.create_task` as of
Phase 6) and its `project_id` existence check both go straight to
`repositories/calendar_events_repository.py` /
`repositories/projects_repository.py`, bypassing the adapter entirely.
Both are inherently Postgres/`audit_logs`-specific bookkeeping
(DevBrain_vision.md §16's idempotency mechanism and an FK-existence
pre-check), not "get calendar data" operations a real provider adapter
would ever need to implement, so they're deliberately kept off the
`CalendarAdapter` Protocol rather than growing it for one internal
callsite.

Human-in-the-loop approval (DevBrain_vision.md §9/§10, Phase 6):
`create_event` is a medium-risk write (see `risk.py`) gated by
`devbrain_common.approvals.enforce_approval` — `Role.ADMIN` callers bypass
(flagged `approval_bypassed_by_admin=true` in the audit row), `Role.USER`
callers must supply a valid `approval_id`.

Security note (ORCHESTRATION.md): `title`/`description`/`location`/`query`
are always treated as opaque text data — never `eval`/`exec`d or passed to
a shell, only ever persisted or ILIKE-matched inside the fake adapter.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from devbrain_common import idempotency as idempotency  # explicit re-export: tests monkeypatch this
from devbrain_common.approvals import enforce_approval
from devbrain_common.audit import record_audit_event
from devbrain_common.auth import Role
from devbrain_common.errors import NotFoundError, ValidationError
from devbrain_common.models import CalendarEvent
from sqlalchemy.ext.asyncio import AsyncSession

from calendar_mcp.adapters.fake_calendar import FakeCalendarAdapter
from calendar_mcp.adapters.protocol import CalendarAdapter, CalendarEventRecord
from calendar_mcp.repositories import calendar_events_repository as calendar_events_repository
from calendar_mcp.repositories import projects_repository as projects_repository
from calendar_mcp.repositories import unit_of_work as uow


def get_adapter(session: AsyncSession) -> CalendarAdapter:
    """Factory: today always returns the Postgres-backed fake adapter.

    The one-line swap for DevBrain_vision.md §24 ("Later connect Google
    Calendar or another real provider"):

        return RealCalendarAdapter(get_settings())

    in place of the line below — nothing else in this service (or the
    `tools/` layer above it) would need to change, since both adapters
    implement the same `CalendarAdapter` Protocol.
    """
    return FakeCalendarAdapter(session)


@dataclass(frozen=True)
class CalendarEventDTO:
    id: str
    project_id: str | None
    title: str
    starts_at: datetime
    ends_at: datetime
    participants: list[str] | None
    location: str | None
    description: str | None
    created_at: datetime | None = None


def _record_to_dto(record: CalendarEventRecord) -> CalendarEventDTO:
    return CalendarEventDTO(
        id=str(record.id),
        project_id=str(record.project_id) if record.project_id else None,
        title=record.title,
        starts_at=record.starts_at,
        ends_at=record.ends_at,
        participants=record.participants,
        location=record.location,
        description=record.description,
        created_at=record.created_at,
    )


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError(f"{field_name!r} is not a valid UUID: {value!r}") from exc


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"{field_name!r} is not a valid ISO 8601 datetime: {value!r}"
        raise ValidationError(msg) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


async def get_today_events() -> list[CalendarEventDTO]:
    """Events starting today (UTC calendar day)."""
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        records = await adapter.list_events_between(
            starts_after=start_of_day, starts_before=end_of_day, limit=200
        )
        return [_record_to_dto(r) for r in records]


async def get_week_events() -> list[CalendarEventDTO]:
    """Events starting in the rolling 7-day window `[today 00:00 UTC, +7 days)`.

    Decision (documented in PROGRESS_REPORT.md Phase 5): "week" here means a
    rolling 7-day-ahead window anchored on today, not a Mon-Sun calendar
    week — matches the "what's coming up" framing a developer briefing tool
    (DevBrain_vision.md §11.5) would want, and needs no ISO-week-boundary
    logic.
    """
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_window = start_of_day + timedelta(days=7)
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        records = await adapter.list_events_between(
            starts_after=start_of_day, starts_before=end_of_window, limit=200
        )
        return [_record_to_dto(r) for r in records]


async def find_event(*, query: str, limit: int = 20) -> list[CalendarEventDTO]:
    if not query.strip():
        raise ValidationError("query must not be empty.")
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        records = await adapter.find_event(query=query, limit=limit)
        return [_record_to_dto(r) for r in records]


def _row_to_dto(row: CalendarEvent) -> CalendarEventDTO:
    """Convert a `CalendarEvent` ORM row straight to a DTO — used only by
    the idempotent-replay path in `create_event`, which reads via
    `calendar_events_repository` directly (see module docstring)."""
    return CalendarEventDTO(
        id=str(row.id),
        project_id=str(row.project_id) if row.project_id else None,
        title=row.title,
        starts_at=row.start_time,
        ends_at=row.end_time,
        participants=row.participants,
        location=row.location,
        description=row.description,
        created_at=row.created_at,
    )


async def create_event(
    *,
    title: str,
    starts_at: str,
    ends_at: str,
    project_id: str | None = None,
    participants: list[str] | None = None,
    location: str | None = None,
    description: str | None = None,
    idempotency_key: str | None = None,
    actor: str,
    role: Role,
    approval_id: str | None = None,
) -> CalendarEventDTO:
    if not title.strip():
        raise ValidationError("title must not be empty.")
    parsed_starts_at = _parse_datetime(starts_at, "starts_at")
    parsed_ends_at = _parse_datetime(ends_at, "ends_at")
    if parsed_ends_at <= parsed_starts_at:
        raise ValidationError("ends_at must be after starts_at.")

    call_arguments = {
        "title": title,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "project_id": project_id,
        "participants": participants,
        "location": location,
        "description": description,
    }

    started = time.monotonic()
    async with uow.unit_of_work() as session:
        replay = await idempotency.check_idempotent_replay(
            session,
            actor=actor,
            tool_name="create_event",
            idempotency_key=idempotency_key,
            result_key="result_event_id",
            get_existing=lambda s, id_str: calendar_events_repository.get_by_id(
                s, uuid.UUID(id_str)
            ),
            started=started,
        )
        if replay is not None:
            return _row_to_dto(replay)

        # Phase 6 human-in-the-loop gate (devbrain_common.approvals):
        # Role.ADMIN bypasses (flagged in the audit row below); Role.USER
        # must supply a valid, matching, unconsumed approval_id or this
        # raises ApprovalRequiredError before anything is mutated.
        bypassed_as_admin = await enforce_approval(
            session,
            role=role,
            actor=actor,
            tool_name="create_event",
            arguments=call_arguments,
            approval_id=approval_id,
        )

        parsed_project_id = _parse_uuid(project_id, "project_id") if project_id else None
        if parsed_project_id is not None and not await projects_repository.exists(
            session, parsed_project_id
        ):
            raise NotFoundError(f"Project {project_id!r} not found.")

        adapter = get_adapter(session)
        record = await adapter.create_event(
            title=title.strip(),
            starts_at=parsed_starts_at,
            ends_at=parsed_ends_at,
            project_id=parsed_project_id,
            participants=participants,
            location=location,
            description=description,
        )
        dto = _record_to_dto(record)

        await record_audit_event(
            session,
            actor=actor,
            tool_name="create_event",
            arguments={
                "title": title,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "idempotency_key": idempotency_key,
                "result_event_id": dto.id,
                "approval_id": approval_id,
                "approval_bypassed_by_admin": bypassed_as_admin,
            },
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return dto
