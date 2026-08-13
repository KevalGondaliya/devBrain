"""Meeting search + read (DevBrain_vision.md §11.1: `search_meetings`,
`read_meeting`). Read-only — Knowledge MCP does not create/edit meetings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from devbrain_common.errors import NotFoundError, ValidationError
from devbrain_common.models import Meeting

from knowledge_mcp.repositories import meetings_repository as meetings_repository
from knowledge_mcp.repositories import unit_of_work as uow


@dataclass(frozen=True)
class MeetingDTO:
    id: str
    project_id: str | None
    title: str
    date: str
    duration_minutes: int | None
    participants: list[str] = field(default_factory=list)
    summary: str | None = None


def _to_dto(meeting: Meeting) -> MeetingDTO:
    return MeetingDTO(
        id=str(meeting.id),
        project_id=str(meeting.project_id) if meeting.project_id else None,
        title=meeting.title,
        date=meeting.date.isoformat(),
        duration_minutes=meeting.duration_minutes,
        participants=list(meeting.participants or []),
        summary=meeting.summary,
    )


async def search_meetings(*, query: str, limit: int = 10) -> list[MeetingDTO]:
    if not query.strip():
        raise ValidationError("query must not be empty.")
    if limit < 1 or limit > 100:
        raise ValidationError("limit must be between 1 and 100.")
    async with uow.unit_of_work() as session:
        rows = await meetings_repository.search(session, query, limit)
        return [_to_dto(m) for m in rows]


async def read_meeting(*, meeting_id: str) -> MeetingDTO:
    try:
        meeting_uuid = uuid.UUID(meeting_id)
    except ValueError as exc:
        raise ValidationError(f"meeting_id is not a valid UUID: {meeting_id!r}") from exc
    async with uow.unit_of_work() as session:
        meeting = await meetings_repository.get_by_id(session, meeting_uuid)
        if meeting is None:
            raise NotFoundError("Meeting not found.")
        return _to_dto(meeting)
