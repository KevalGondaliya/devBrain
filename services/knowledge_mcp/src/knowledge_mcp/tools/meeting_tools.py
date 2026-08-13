"""`search_meetings`/`read_meeting` — DevBrain_vision.md §11.1."""

from __future__ import annotations

from typing import Annotated, Any

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from knowledge_mcp.auth import require_min_role
from knowledge_mcp.services import meetings_service
from knowledge_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="search_meetings", description="Keyword search over meeting titles/summaries.")
    @handle_tool_errors
    async def search_meetings(
        query: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        meetings = await meetings_service.search_meetings(query=query, limit=limit)
        return {"meetings": [dto_to_dict(m) for m in meetings]}

    @mcp.tool(name="read_meeting", description="Fetch one meeting by id.")
    @handle_tool_errors
    async def read_meeting(
        meeting_id: str, ctx: Context[Any, Any, Any] | None = None
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        meeting = await meetings_service.read_meeting(meeting_id=meeting_id)
        return dto_to_dict(meeting)
