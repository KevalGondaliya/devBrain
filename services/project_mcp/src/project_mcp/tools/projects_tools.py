"""`list_projects`/`search_projects`/`get_project`/`get_project_status`/
`update_project_status` tools — `DevBrain_vision.md` §11.2. Flat (undotted)
tool names, exactly as that section names them (no `projects.*` namespace —
that convention belongs to Knowledge MCP's `second-brain-mcp-plan.md` §4
tools, not this one)."""

from __future__ import annotations

from typing import Annotated, Any

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from project_mcp.auth import require_min_role
from project_mcp.risk import approval_required
from project_mcp.services import projects_service
from project_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="list_projects", description="List every project.")
    @handle_tool_errors
    async def list_projects(ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        projects = await projects_service.list_projects()
        return {"projects": [dto_to_dict(p) for p in projects]}

    @mcp.tool(name="search_projects", description="Keyword search over project name/description.")
    @handle_tool_errors
    async def search_projects(
        query: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        projects = await projects_service.search_projects(query=query, limit=limit)
        return {"results": [dto_to_dict(p) for p in projects]}

    @mcp.tool(name="get_project", description="Fetch a single project by id.")
    @handle_tool_errors
    async def get_project(id: str, ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        project = await projects_service.get_project(project_id=id)
        return dto_to_dict(project)

    @mcp.tool(name="get_project_status", description="Fetch a project's current status.")
    @handle_tool_errors
    async def get_project_status(
        id: str, ctx: Context[Any, Any, Any] | None = None
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        status = await projects_service.get_project_status(project_id=id)
        return dto_to_dict(status)

    @mcp.tool(
        name="update_project_status",
        description=(
            "Update a project's status, with an optional human-readable reason. "
            "Medium risk: Role.USER callers must pass a valid approval_id obtained "
            "from request_approval (same project_id/status/reason); Role.ADMIN callers "
            "may call this directly (the bypass is recorded in the audit log)."
        ),
    )
    @handle_tool_errors
    async def update_project_status(
        id: str,
        status: str,
        reason: str | None = None,
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        project = await projects_service.update_project_status(
            project_id=id,
            status=status,
            reason=reason,
            actor=actor_ctx.actor,
            role=actor_ctx.role,
            approval_id=approval_id,
        )
        return {
            **dto_to_dict(project),
            "risk_tier": "medium",
            "approval_recommended": approval_required("update_project_status"),
        }
