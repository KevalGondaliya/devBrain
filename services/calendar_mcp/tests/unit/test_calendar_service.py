"""`calendar_service` orchestration — the adapter is mocked out via
`get_adapter`, and deliberately *not* `FakeCalendarAdapter`: `DoubleAdapter`
below is a hand-written double that implements the `CalendarAdapter`
Protocol on its own terms (no shared base class, no import of
`FakeCalendarAdapter` at all). If these tests pass, `calendar_service`
genuinely only depends on the Protocol's shape for its four public
operations, not on any concrete adapter class — proving the fake/real
adapter seam described in `adapters/protocol.py`'s module docstring is
real, not just documented.

`create_event`'s idempotency-key/project-existence bookkeeping bypasses the
adapter by design (see `calendar_service.py`'s module docstring) — those
tests mock `calendar_events_repository`/`projects_repository`/
`idempotency_repository` directly instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from calendar_mcp.adapters.protocol import CalendarEventRecord
from calendar_mcp.services import calendar_service
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, NotFoundError, ValidationError


@dataclass
class DoubleAdapter:
    """A `CalendarAdapter`-shaped double independent of `FakeCalendarAdapter`."""

    events: list[CalendarEventRecord] = field(default_factory=list)
    found: list[CalendarEventRecord] = field(default_factory=list)
    created: CalendarEventRecord | None = None
    seen_calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    async def list_events_between(
        self, *, starts_after: datetime, starts_before: datetime, limit: int
    ) -> list[CalendarEventRecord]:
        self.seen_calls.append(
            (
                "list_events_between",
                {"starts_after": starts_after, "starts_before": starts_before, "limit": limit},
            )
        )
        return self.events

    async def find_event(self, *, query: str, limit: int) -> list[CalendarEventRecord]:
        self.seen_calls.append(("find_event", {"query": query, "limit": limit}))
        return self.found

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
        self.seen_calls.append(
            (
                "create_event",
                {
                    "title": title,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "project_id": project_id,
                },
            )
        )
        assert self.created is not None
        return self.created


def _record(**overrides: object) -> CalendarEventRecord:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "project_id": None,
        "title": "Standup",
        "starts_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "ends_at": datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        "participants": ["Alice", "Bob"],
        "location": None,
        "description": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return CalendarEventRecord(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def double(monkeypatch: pytest.MonkeyPatch) -> DoubleAdapter:
    adapter = DoubleAdapter()

    def fake_get_adapter(session: object) -> DoubleAdapter:
        return adapter

    monkeypatch.setattr(calendar_service, "get_adapter", fake_get_adapter)
    return adapter


@pytest.fixture(autouse=True)
def _no_real_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_record_audit_event(session: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(calendar_service, "record_audit_event", fake_record_audit_event)


# --- get_today_events / get_week_events ------------------------------------


async def test_get_today_events_uses_a_24h_window(double: DoubleAdapter) -> None:
    double.events = [_record(title="Daily sync")]
    results = await calendar_service.get_today_events()
    assert results[0].title == "Daily sync"

    call_name, kwargs = double.seen_calls[0]
    assert call_name == "list_events_between"
    window = kwargs["starts_before"] - kwargs["starts_after"]  # type: ignore[operator]
    assert window == timedelta(days=1)


async def test_get_week_events_uses_a_7_day_window(double: DoubleAdapter) -> None:
    double.events = [_record(title="Sprint review")]
    results = await calendar_service.get_week_events()
    assert results[0].title == "Sprint review"

    call_name, kwargs = double.seen_calls[0]
    assert call_name == "list_events_between"
    window = kwargs["starts_before"] - kwargs["starts_after"]  # type: ignore[operator]
    assert window == timedelta(days=7)


# --- find_event --------------------------------------------------------


async def test_find_event_rejects_empty_query(double: DoubleAdapter) -> None:
    with pytest.raises(ValidationError):
        await calendar_service.find_event(query="   ")


async def test_find_event_returns_dtos(double: DoubleAdapter) -> None:
    double.found = [_record(title="1:1 with manager")]
    results = await calendar_service.find_event(query="1:1")
    assert results[0].title == "1:1 with manager"


# --- create_event --------------------------------------------------------


async def test_create_event_rejects_empty_title(double: DoubleAdapter) -> None:
    with pytest.raises(ValidationError):
        await calendar_service.create_event(
            title="   ",
            starts_at="2026-01-01T09:00:00+00:00",
            ends_at="2026-01-01T09:30:00+00:00",
            actor="tester",
            role=Role.ADMIN,
        )


async def test_create_event_rejects_end_before_start(double: DoubleAdapter) -> None:
    with pytest.raises(ValidationError):
        await calendar_service.create_event(
            title="Bad event",
            starts_at="2026-01-01T09:30:00+00:00",
            ends_at="2026-01-01T09:00:00+00:00",
            actor="tester",
            role=Role.ADMIN,
        )


async def test_create_event_unknown_project_raises_not_found(
    double: DoubleAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_exists(session: object, project_id: uuid.UUID) -> bool:
        return False

    monkeypatch.setattr(calendar_service.projects_repository, "exists", fake_exists)

    with pytest.raises(NotFoundError):
        await calendar_service.create_event(
            title="Event",
            starts_at="2026-01-01T09:00:00+00:00",
            ends_at="2026-01-01T09:30:00+00:00",
            project_id=str(uuid.uuid4()),
            actor="tester",
            role=Role.ADMIN,
        )


async def test_create_event_happy_path(double: DoubleAdapter) -> None:
    created = _record(title="New event")
    double.created = created

    dto = await calendar_service.create_event(
        title="New event",
        starts_at="2026-01-01T09:00:00+00:00",
        ends_at="2026-01-01T09:30:00+00:00",
        actor="tester",
        role=Role.ADMIN,
    )
    assert dto.title == "New event"
    assert double.seen_calls[-1][0] == "create_event"


async def test_create_event_idempotent_replay_returns_existing_event(
    monkeypatch: pytest.MonkeyPatch, double: DoubleAdapter
) -> None:
    existing_id = uuid.uuid4()

    @dataclass
    class FakeAuditLog:
        arguments: dict[str, object]

    @dataclass
    class FakeRow:
        id: uuid.UUID
        project_id: uuid.UUID | None
        title: str
        start_time: datetime
        end_time: datetime
        participants: list[str] | None
        location: str | None
        description: str | None
        created_at: datetime

    prior_log = FakeAuditLog(
        arguments={"idempotency_key": "abc123", "result_event_id": str(existing_id)}
    )
    existing_row = FakeRow(
        id=existing_id,
        project_id=None,
        title="Original event",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        participants=None,
        location=None,
        description=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    async def fake_find_by_key(
        session: object, *, tool_name: str, idempotency_key: str
    ) -> FakeAuditLog:
        assert tool_name == "create_event"
        assert idempotency_key == "abc123"
        return prior_log

    async def fake_get_by_id(session: object, event_id: uuid.UUID) -> FakeRow:
        assert event_id == existing_id
        return existing_row

    monkeypatch.setattr(
        calendar_service.idempotency, "find_successful_call_by_key", fake_find_by_key
    )
    monkeypatch.setattr(calendar_service.calendar_events_repository, "get_by_id", fake_get_by_id)

    dto = await calendar_service.create_event(
        title="Ignored on replay",
        starts_at="2026-01-01T09:00:00+00:00",
        ends_at="2026-01-01T09:30:00+00:00",
        idempotency_key="abc123",
        actor="tester",
        role=Role.ADMIN,
    )

    assert dto.id == str(existing_id)
    assert dto.title == "Original event"
    assert double.seen_calls == []  # adapter never invoked on replay


# --- Phase 6: approval gate (devbrain_common.approvals) ---------------------


async def test_create_event_user_without_approval_raises_approval_required(
    double: DoubleAdapter,
) -> None:
    """`enforce_approval` raises before the adapter/project lookup — the
    double must never see a call."""
    with pytest.raises(ApprovalRequiredError):
        await calendar_service.create_event(
            title="Needs approval",
            starts_at="2026-01-01T09:00:00+00:00",
            ends_at="2026-01-01T09:30:00+00:00",
            actor="user-bob",
            role=Role.USER,
        )
    assert double.seen_calls == []


async def test_create_event_admin_bypass_is_audited(
    double: DoubleAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _record(title="Admin-created event")
    double.created = created
    recorded: dict[str, object] = {}

    async def fake_record_audit_event(session: object, **kwargs: object) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr(calendar_service, "record_audit_event", fake_record_audit_event)

    await calendar_service.create_event(
        title="Admin-created event",
        starts_at="2026-01-01T09:00:00+00:00",
        ends_at="2026-01-01T09:30:00+00:00",
        actor="admin-alice",
        role=Role.ADMIN,
    )

    assert recorded["arguments"]["approval_bypassed_by_admin"] is True  # type: ignore[index]
