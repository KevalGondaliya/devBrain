"""`RealCalendarAdapter` — confirms it satisfies the same call shape as
`FakeCalendarAdapter` (constructible, same method signatures) while every
operation is a deliberate `NotImplementedError` stub (Phase 24 not built
yet)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from calendar_mcp.adapters.real_calendar import RealCalendarAdapter


def test_constructible_with_arbitrary_args() -> None:
    # The whole point of the stub: constructing it doesn't blow up, so the
    # one-line factory swap in calendar_service.get_adapter() type-checks
    # and runs today even though no method is implemented yet.
    RealCalendarAdapter()
    RealCalendarAdapter("some-client", credentials="abc")


async def test_list_events_between_raises_not_implemented() -> None:
    adapter = RealCalendarAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.list_events_between(
            starts_after=datetime(2026, 1, 1, tzinfo=UTC),
            starts_before=datetime(2026, 1, 2, tzinfo=UTC),
            limit=10,
        )


async def test_find_event_raises_not_implemented() -> None:
    adapter = RealCalendarAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.find_event(query="x", limit=10)


async def test_create_event_raises_not_implemented() -> None:
    adapter = RealCalendarAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.create_event(
            title="x",
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
            project_id=uuid.uuid4(),
            participants=None,
            location=None,
            description=None,
        )
