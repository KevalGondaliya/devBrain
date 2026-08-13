"""Stub for a real-provider-backed `CalendarAdapter` (DevBrain_vision.md
§21 + §24 "Real Integrations": "Fake Calendar -> Google Calendar API").

Not implemented yet — every method raises `NotImplementedError`. This file
exists now so the *seam* is real and reviewable: `RealCalendarAdapter`
implements the exact same `CalendarAdapter` Protocol
(`adapters/protocol.py`) as `FakeCalendarAdapter`
(`adapters/fake_calendar.py`), so swapping which one
`calendar_service.py`'s `get_adapter()` factory returns is a one-line
change, not a service-layer rewrite — the whole point of
DevBrain_vision.md §21's adapter architecture.

Where a real implementation plugs in, when this is picked up:
  - `__init__` would take an authenticated Google Calendar client (e.g.
    `google-api-python-client`'s `build("calendar", "v3", credentials=...)`)
    — the OAuth credentials/refresh token would be read from
    `devbrain_common.config.Settings` (new fields there, following the same
    pattern as `ANTHROPIC_API_KEY`), never hardcoded, per
    ORCHESTRATION.md's secrets rule.
  - `list_events_between`/`find_event` would call `events().list(...)` on
    the target calendar (with `timeMin`/`timeMax` or `q=` params) and
    translate each API `Event` resource into a `CalendarEventRecord` — the
    same shape `FakeCalendarAdapter` already returns, so nothing above the
    adapter layer (`calendar_service.py`, `tools/calendar_tools.py`) would
    need to change.
  - `create_event` would call `events().insert(...)`.
  - Real-integration-specific security concerns (DevBrain_vision.md §22):
    OAuth/token rotation, SSRF protection on any user-influenced URL
    construction, and network egress rules would all be handled inside
    this adapter, not leaked into the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from calendar_mcp.adapters.protocol import CalendarEventRecord

_NOT_IMPLEMENTED = (
    "RealCalendarAdapter is a Phase 24 stub — the live Google Calendar (or "
    "other provider) integration has not been built yet. FakeCalendarAdapter "
    "(Postgres-backed synthetic data) is what's actually wired up today; see "
    "calendar_service.get_adapter()."
)


class RealCalendarAdapter:
    """Not-yet-implemented `CalendarAdapter` over a real provider API. See module docstring.

    `__init__` deliberately does *not* raise — it accepts (and ignores) the
    future client/credentials args so the one-line swap in
    `calendar_service.get_adapter()` (`return RealCalendarAdapter(...)`
    instead of `FakeCalendarAdapter(session)`) is a real, type-checkable
    statement today, not just a comment. Every actual operation raises
    `NotImplementedError` when called.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def list_events_between(
        self, *, starts_after: datetime, starts_before: datetime, limit: int
    ) -> list[CalendarEventRecord]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    async def find_event(self, *, query: str, limit: int) -> list[CalendarEventRecord]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

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
        raise NotImplementedError(_NOT_IMPLEMENTED)
