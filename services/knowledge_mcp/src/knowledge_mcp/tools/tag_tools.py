"""`tags.*` tools — second-brain-mcp-plan.md §4."""

from __future__ import annotations

from typing import Annotated, Any

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from knowledge_mcp.auth import require_min_role
from knowledge_mcp.risk import approval_required
from knowledge_mcp.services import tags_service
from knowledge_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="tags.list", description="List every tag with its (non-deleted) note count.")
    @handle_tool_errors
    async def tags_list(ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        tags = await tags_service.list_tags()
        return {"tags": [dto_to_dict(t) for t in tags]}

    @mcp.tool(
        name="tags.rename",
        description=(
            "Rename a tag, merging into an existing tag if the new name "
            "collides. Medium risk: Role.USER callers must pass a valid "
            "approval_id obtained from request_approval (arguments: "
            "old_name/new_name); Role.ADMIN callers may call this directly "
            "(the bypass is recorded in the audit log)."
        ),
    )
    @handle_tool_errors
    async def tags_rename(
        old_name: Annotated[str, Field(min_length=1)],
        new_name: Annotated[str, Field(min_length=1)],
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        tag = await tags_service.rename_tag(
            old_name=old_name,
            new_name=new_name,
            actor=actor_ctx.actor,
            role=actor_ctx.role,
            approval_id=approval_id,
        )
        return {
            **dto_to_dict(tag),
            "risk_tier": "medium",
            "approval_recommended": approval_required("tags.rename"),
        }
