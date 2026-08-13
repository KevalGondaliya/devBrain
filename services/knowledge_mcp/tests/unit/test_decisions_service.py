"""`decisions_service` — repository mocked."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from _fakes import fake_unit_of_work
from devbrain_common.errors import NotFoundError, ValidationError
from knowledge_mcp.repositories import unit_of_work as uow
from knowledge_mcp.services import decisions_service


@dataclass
class FakeDecision:
    id: uuid.UUID
    project_id: uuid.UUID | None
    meeting_id: uuid.UUID | None
    title: str
    decision: str
    reasoning: str | None
    date: datetime
    status: str


@pytest.fixture(autouse=True)
def _patch_unit_of_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uow, "unit_of_work", fake_unit_of_work)


async def test_search_decisions_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        await decisions_service.search_decisions(query="")


async def test_search_decisions_returns_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = FakeDecision(
        id=uuid.uuid4(),
        project_id=None,
        meeting_id=None,
        title="Use Postgres",
        decision="We will use Postgres.",
        reasoning="Relational + pgvector.",
        date=datetime.now(tz=UTC),
        status="accepted",
    )

    async def fake_search(session: object, query: str, limit: int) -> list[FakeDecision]:
        return [decision]

    monkeypatch.setattr(decisions_service.decisions_repository, "search", fake_search)

    results = await decisions_service.search_decisions(query="postgres")
    assert len(results) == 1
    assert results[0].status == "accepted"


async def test_get_decision_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, decision_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(decisions_service.decisions_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await decisions_service.get_decision(decision_id=str(uuid.uuid4()))


async def test_get_decision_invalid_uuid_raises_validation() -> None:
    with pytest.raises(ValidationError):
        await decisions_service.get_decision(decision_id="not-a-uuid")
