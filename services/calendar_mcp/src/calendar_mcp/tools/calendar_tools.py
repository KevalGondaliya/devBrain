"""`get_today_events`/`get_week_events`/`find_event`/`create_event` tools —
`DevBrain_vision.md` §11.5. Flat (undotted) tool names, exactly as that
section names them."""

from __future__ import annotations

from typing import Annotated, Any

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from calendar_mcp.auth import require_min_role
from calendar_mcp.risk import approval_required
from calendar_mcp.services import calendar_service
from calendar_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="get_today_events", description="List calendar events starting today (UTC).")
    @handle_tool_errors
    async def get_today_events(ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        events = await calendar_service.get_today_events()
        return {"events": [dto_to_dict(e) for e in events]}

    @mcp.tool(
        name="get_week_events",
        description="List calendar events starting in the next 7 days (rolling window, UTC).",
    )
    @handle_tool_errors
    async def get_week_events(ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        events = await calendar_service.get_week_events()
        return {"events": [dto_to_dict(e) for e in events]}

    @mcp.tool(
        name="find_event", description="Keyword search over event title/description/location."
    )
    @handle_tool_errors
    async def find_event(
        query: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        events = await calendar_service.find_event(query=query, limit=limit)
        return {"results": [dto_to_dict(e) for e in events]}

    @mcp.tool(
        name="create_event",
        description=(
            "Create a new calendar event. Accepts an optional `idempotency_key` — "
            "a retried call with the same key returns the already-created event "
            "instead of making a duplicate. Medium risk: Role.USER callers must pass "
            "a valid approval_id obtained from request_approval (matching arguments "
            "exactly); Role.ADMIN callers may call this directly (the bypass is "
            "recorded in the audit log)."
        ),
    )
    @handle_tool_errors
    async def create_event(
        title: Annotated[str, Field(min_length=1, max_length=300)],
        starts_at: str,
        ends_at: str,
        project_id: str | None = None,
        participants: list[str] | None = None,
        location: str | None = None,
        description: str | None = None,
        idempotency_key: str | None = None,
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        event = await calendar_service.create_event(
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            project_id=project_id,
            participants=participants,
            location=location,
            description=description,
            idempotency_key=idempotency_key,
            actor=actor_ctx.actor,
            role=actor_ctx.role,
            approval_id=approval_id,
        )
        return {
            **dto_to_dict(event),
            "risk_tier": "medium",
            "approval_recommended": approval_required("create_event"),
        }
