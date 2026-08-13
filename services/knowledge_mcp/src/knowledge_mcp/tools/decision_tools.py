"""`search_decisions`/`get_decision` — DevBrain_vision.md §11.1."""

from __future__ import annotations

from typing import Annotated, Any

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from knowledge_mcp.auth import require_min_role
from knowledge_mcp.services import decisions_service
from knowledge_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="search_decisions",
        description="Keyword search over decision titles/text/reasoning.",
    )
    @handle_tool_errors
    async def search_decisions(
        query: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        decisions = await decisions_service.search_decisions(query=query, limit=limit)
        return {"decisions": [dto_to_dict(d) for d in decisions]}

    @mcp.tool(name="get_decision", description="Fetch one decision by id.")
    @handle_tool_errors
    async def get_decision(
        decision_id: str, ctx: Context[Any, Any, Any] | None = None
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        decision = await decisions_service.get_decision(decision_id=decision_id)
        return dto_to_dict(decision)
