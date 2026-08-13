"""The seam between `services/calendar_service.py` and where calendar data
actually comes from (DevBrain_vision.md §21 "Adapter Architecture" +
§11.5/§24).

`CalendarAdapter` is a `Protocol` (structural typing — no inheritance
needed) describing exactly the operations the service layer needs,
independent of whether the implementation reads Postgres
(`FakeCalendarAdapter`, what's actually wired up today) or calls a real
provider like Google Calendar (`RealCalendarAdapter`, a stub until Phase
24). `calendar_service.py` imports only this Protocol and
`CalendarEventRecord` — never a concrete adapter class — so swapping fake ->
real later is a one-line change in `calendar_service.get_adapter()`, not a
service-layer rewrite. Mirrors
`services/github_mcp/src/github_mcp/adapters/protocol.py` exactly.

`CalendarEventRecord` is the shared data shape both adapters return/accept.
It uses the public tool vocabulary (`starts_at`/`ends_at`, matching
`DevBrain_vision.md` §11.5's `create_event(title, starts_at, ends_at, ...)`
signature), not the DB column names (`start_time`/`end_time` — see
`devbrain_common.models.CalendarEvent`) — that DB-column <-> public-name
translation happens entirely inside `FakeCalendarAdapter`/the repository
layer, so nothing above the adapter layer needs to know the storage schema.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CalendarEventRecord:
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    starts_at: datetime
    ends_at: datetime
    participants: list[str] | None
    location: str | None
    description: str | None
    created_at: datetime | None


class CalendarAdapter(Protocol):
    """Structural interface every calendar data source (fake or real) implements."""

    async def list_events_between(
        self, *, starts_after: datetime, starts_before: datetime, limit: int
    ) -> list[CalendarEventRecord]: ...

    async def find_event(self, *, query: str, limit: int) -> list[CalendarEventRecord]: ...

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
    ) -> CalendarEventRecord: ...
