"""`FakeCalendarAdapter` — the ORM-row <-> `CalendarEventRecord` translation
(including the `start_time`/`end_time` <-> `starts_at`/`ends_at` name
mapping), with `repositories.calendar_events_repository` mocked out
(no DB)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from calendar_mcp.adapters import fake_calendar


@dataclass
class FakeRow:
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    start_time: datetime
    end_time: datetime
    participants: list[str] | None = None
    location: str | None = None
    description: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


async def test_list_events_between_delegates_and_translates_field_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    row = FakeRow(
        id=uuid.uuid4(),
        project_id=None,
        title="Standup",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
    )

    async def fake_list_starting_between(
        session: object, *, starts_after: datetime, starts_before: datetime, limit: int
    ) -> list[FakeRow]:
        seen.update({"starts_after": starts_after, "starts_before": starts_before, "limit": limit})
        return [row]

    monkeypatch.setattr(
        fake_calendar.calendar_events_repository,
        "list_starting_between",
        fake_list_starting_between,
    )

    adapter = fake_calendar.FakeCalendarAdapter(session=object())  # type: ignore[arg-type]
    results = await adapter.list_events_between(
        starts_after=datetime(2026, 1, 1, tzinfo=UTC),
        starts_before=datetime(2026, 1, 2, tzinfo=UTC),
        limit=200,
    )

    assert results[0].starts_at == row.start_time
    assert results[0].ends_at == row.end_time
    assert seen["limit"] == 200


async def test_find_event_delegates_to_search(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    row = FakeRow(
        id=uuid.uuid4(),
        project_id=None,
        title="1:1",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
    )

    async def fake_search(session: object, *, query: str, limit: int) -> list[FakeRow]:
        seen.update({"query": query, "limit": limit})
        return [row]

    monkeypatch.setattr(fake_calendar.calendar_events_repository, "search", fake_search)

    adapter = fake_calendar.FakeCalendarAdapter(session=object())  # type: ignore[arg-type]
    results = await adapter.find_event(query="1:1", limit=10)

    assert seen == {"query": "1:1", "limit": 10}
    assert results[0].title == "1:1"


async def test_create_event_inserts_and_returns_translated_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserted: list[object] = []

    def fake_insert(session: object, event: object) -> None:
        inserted.append(event)

    monkeypatch.setattr(fake_calendar.calendar_events_repository, "insert", fake_insert)

    class FakeSession:
        async def flush(self) -> None:
            return None

    adapter = fake_calendar.FakeCalendarAdapter(session=FakeSession())  # type: ignore[arg-type]
    record = await adapter.create_event(
        title="New event",
        starts_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        ends_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        project_id=None,
        participants=["Alice"],
        location=None,
        description=None,
    )

    assert len(inserted) == 1
    assert record.title == "New event"
    assert record.starts_at == datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    assert record.participants == ["Alice"]
