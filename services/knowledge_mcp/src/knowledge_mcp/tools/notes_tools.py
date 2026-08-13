"""`notes.*` tools — second-brain-mcp-plan.md §4."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from knowledge_mcp.auth import require_min_role
from knowledge_mcp.risk import approval_required
from knowledge_mcp.services import notes_service, search_service
from knowledge_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="notes.create",
        description=(
            "Create a new note with markdown content and tags. Medium risk: "
            "Role.USER callers must pass a valid approval_id obtained from "
            "request_approval (arguments: title/content_md/tags/project_id/"
            "note_type); Role.ADMIN callers may call this directly (the bypass "
            "is recorded in the audit log)."
        ),
    )
    @handle_tool_errors
    async def notes_create(
        title: Annotated[str, Field(min_length=1, max_length=300)],
        content_md: Annotated[str, Field(min_length=1)],
        tags: list[str] | None = None,
        project_id: str | None = None,
        type: Literal["learning", "architecture", "technical", "idea", "personal"] = "technical",
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        note = await notes_service.create_note(
            title=title,
            content_md=content_md,
            tags=tags or [],
            project_id=project_id,
            note_type=type,
            actor=actor_ctx.actor,
            role=actor_ctx.role,
            approval_id=approval_id,
        )
        return {
            **dto_to_dict(note),
            "risk_tier": "medium",
            "approval_recommended": approval_required("notes.create"),
        }

    @mcp.tool(name="notes.get", description="Fetch a note by id or slug.")
    @handle_tool_errors
    async def notes_get(
        id: str | None = None,
        slug: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        note = await notes_service.get_note(note_id=id, slug=slug)
        return dto_to_dict(note)

    @mcp.tool(
        name="notes.update",
        description=(
            "Partially update a note's title/content/tags/type. Medium risk: "
            "Role.USER callers must pass a valid approval_id obtained from "
            "request_approval (matching arguments exactly); Role.ADMIN callers "
            "may call this directly (the bypass is recorded in the audit log)."
        ),
    )
    @handle_tool_errors
    async def notes_update(
        id: str,
        title: str | None = None,
        content_md: str | None = None,
        tags: list[str] | None = None,
        type: Literal["learning", "architecture", "technical", "idea", "personal"] | None = None,
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        note = await notes_service.update_note(
            note_id=id,
            title=title,
            content_md=content_md,
            tags=tags,
            note_type=type,
            actor=actor_ctx.actor,
            role=actor_ctx.role,
            approval_id=approval_id,
        )
        return {
            **dto_to_dict(note),
            "risk_tier": "medium",
            "approval_recommended": approval_required("notes.update"),
        }

    @mcp.tool(
        name="notes.delete",
        description=(
            "Soft-delete a note (sets deleted_at). High risk: requires "
            "Role.ADMIN *and* a valid approval_id obtained from request_approval "
            "(arguments: {'note_id': id}) — unlike medium-risk writes, admin "
            "status alone does not bypass the approval requirement here."
        ),
    )
    @handle_tool_errors
    async def notes_delete(
        id: str,
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.ADMIN)
        await notes_service.delete_note(
            note_id=id, actor=actor_ctx.actor, role=actor_ctx.role, approval_id=approval_id
        )
        return {
            "id": id,
            "deleted": True,
            "risk_tier": "high",
            "approval_recommended": approval_required("notes.delete"),
        }

    @mcp.tool(
        name="notes.search",
        description="Hybrid keyword+semantic (or single-mode) search over notes.",
    )
    @handle_tool_errors
    async def notes_search(
        query: Annotated[str, Field(min_length=1)],
        mode: Literal["hybrid", "keyword", "semantic"] = "hybrid",
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        hits = await search_service.search_notes(query=query, mode=mode, limit=limit)
        return {"results": [dto_to_dict(hit) for hit in hits]}
