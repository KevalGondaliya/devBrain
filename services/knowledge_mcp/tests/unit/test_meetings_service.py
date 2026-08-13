"""`meetings_service` — repository mocked."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from _fakes import fake_unit_of_work
from devbrain_common.errors import NotFoundError, ValidationError
from knowledge_mcp.repositories import unit_of_work as uow
from knowledge_mcp.services import meetings_service


@dataclass
class FakeMeeting:
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    date: datetime
    duration_minutes: int | None
    participants: list[str] | None
    summary: str | None


@pytest.fixture(autouse=True)
def _patch_unit_of_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uow, "unit_of_work", fake_unit_of_work)


async def test_search_meetings_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        await meetings_service.search_meetings(query="  ")


async def test_search_meetings_returns_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    meeting = FakeMeeting(
        id=uuid.uuid4(),
        project_id=None,
        title="Sprint planning",
        date=datetime.now(tz=UTC),
        duration_minutes=30,
        participants=["Alex", "Sam"],
        summary="Planned the sprint.",
    )

    async def fake_search(session: object, query: str, limit: int) -> list[FakeMeeting]:
        return [meeting]

    monkeypatch.setattr(meetings_service.meetings_repository, "search", fake_search)

    results = await meetings_service.search_meetings(query="sprint")
    assert len(results) == 1
    assert results[0].title == "Sprint planning"
    assert results[0].participants == ["Alex", "Sam"]


async def test_read_meeting_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, meeting_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(meetings_service.meetings_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await meetings_service.read_meeting(meeting_id=str(uuid.uuid4()))


async def test_read_meeting_invalid_uuid_raises_validation() -> None:
    with pytest.raises(ValidationError):
        await meetings_service.read_meeting(meeting_id="not-a-uuid")
