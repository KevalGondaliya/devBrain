"""Decision search + get (DevBrain_vision.md §11.1: `search_decisions`,
`get_decision`). Read-only — Knowledge MCP does not create/edit decisions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from devbrain_common.errors import NotFoundError, ValidationError
from devbrain_common.models import Decision

from knowledge_mcp.repositories import decisions_repository as decisions_repository
from knowledge_mcp.repositories import unit_of_work as uow


@dataclass(frozen=True)
class DecisionDTO:
    id: str
    project_id: str | None
    meeting_id: str | None
    title: str
    decision: str
    reasoning: str | None
    date: str
    status: str


def _to_dto(decision: Decision) -> DecisionDTO:
    return DecisionDTO(
        id=str(decision.id),
        project_id=str(decision.project_id) if decision.project_id else None,
        meeting_id=str(decision.meeting_id) if decision.meeting_id else None,
        title=decision.title,
        decision=decision.decision,
        reasoning=decision.reasoning,
        date=decision.date.isoformat(),
        status=decision.status,
    )


async def search_decisions(*, query: str, limit: int = 10) -> list[DecisionDTO]:
    if not query.strip():
        raise ValidationError("query must not be empty.")
    if limit < 1 or limit > 100:
        raise ValidationError("limit must be between 1 and 100.")
    async with uow.unit_of_work() as session:
        rows = await decisions_repository.search(session, query, limit)
        return [_to_dto(d) for d in rows]


async def get_decision(*, decision_id: str) -> DecisionDTO:
    try:
        decision_uuid = uuid.UUID(decision_id)
    except ValueError as exc:
        raise ValidationError(f"decision_id is not a valid UUID: {decision_id!r}") from exc
    async with uow.unit_of_work() as session:
        decision = await decisions_repository.get_by_id(session, decision_uuid)
        if decision is None:
            raise NotFoundError("Decision not found.")
        return _to_dto(decision)
