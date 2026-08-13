"""`links.*` tools — second-brain-mcp-plan.md §4."""

from __future__ import annotations

from typing import Annotated, Any

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from knowledge_mcp.auth import require_min_role
from knowledge_mcp.services import links_service
from knowledge_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="links.get_backlinks",
        description="List every note that links to the given note.",
    )
    @handle_tool_errors
    async def links_get_backlinks(
        note_id: str, ctx: Context[Any, Any, Any] | None = None
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        backlinks = await links_service.get_backlinks(note_id=note_id)
        return {"backlinks": [dto_to_dict(b) for b in backlinks]}

    @mcp.tool(
        name="links.get_graph",
        description="Obsidian-style subgraph traversal from a note out to `depth` hops.",
    )
    @handle_tool_errors
    async def links_get_graph(
        note_id: str,
        depth: Annotated[int, Field(ge=1, le=5)] = 2,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        graph = await links_service.get_graph(note_id=note_id, depth=depth)
        return dto_to_dict(graph)
