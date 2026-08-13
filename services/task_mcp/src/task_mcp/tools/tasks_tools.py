"""`list_tasks`/`search_tasks`/`get_task`/`create_task`/`update_task`/
`complete_task` tools — `DevBrain_vision.md` §11.3. Flat (undotted) tool
names, exactly as that section names them."""

from __future__ import annotations

from typing import Annotated, Any

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from task_mcp.auth import require_min_role
from task_mcp.risk import approval_required
from task_mcp.services import tasks_service
from task_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="list_tasks",
        description="List tasks, optionally filtered by project and/or status.",
    )
    @handle_tool_errors
    async def list_tasks(
        project_id: str | None = None,
        status: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        tasks = await tasks_service.list_tasks(project_id=project_id, status=status)
        return {"tasks": [dto_to_dict(t) for t in tasks]}

    @mcp.tool(name="search_tasks", description="Keyword search over task title/description.")
    @handle_tool_errors
    async def search_tasks(
        query: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        tasks = await tasks_service.search_tasks(query=query, limit=limit)
        return {"results": [dto_to_dict(t) for t in tasks]}

    @mcp.tool(name="get_task", description="Fetch a single task by id.")
    @handle_tool_errors
    async def get_task(id: str, ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        task = await tasks_service.get_task(task_id=id)
        return dto_to_dict(task)

    @mcp.tool(
        name="create_task",
        description=(
            "Create a new task under a project. Accepts an optional "
            "`idempotency_key` — a retried call with the same key returns "
            "the already-created task instead of making a duplicate. "
            "Medium risk: Role.USER callers must pass a valid approval_id obtained "
            "from request_approval (arguments: project_id/title/description/priority/"
            "assignee/due_date); Role.ADMIN callers may call this directly (the "
            "bypass is recorded in the audit log)."
        ),
    )
    @handle_tool_errors
    async def create_task(
        project_id: str,
        title: Annotated[str, Field(min_length=1, max_length=300)],
        description: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
        idempotency_key: str | None = None,
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        task = await tasks_service.create_task(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            assignee=assignee,
            due_date=due_date,
            idempotency_key=idempotency_key,
            actor=actor_ctx.actor,
            role=actor_ctx.role,
            approval_id=approval_id,
        )
        return {
            **dto_to_dict(task),
            "risk_tier": "medium",
            "approval_recommended": approval_required("create_task"),
        }

    @mcp.tool(
        name="update_task",
        description=(
            "Partially update a task's title/description/status/priority/"
            "assignee/due_date/blocked_reason. Medium risk: Role.USER callers must "
            "pass a valid approval_id obtained from request_approval (matching "
            "arguments exactly); Role.ADMIN callers may call this directly (the "
            "bypass is recorded in the audit log)."
        ),
    )
    @handle_tool_errors
    async def update_task(
        id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
        blocked_reason: str | None = None,
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        task = await tasks_service.update_task(
            task_id=id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignee=assignee,
            due_date=due_date,
            blocked_reason=blocked_reason,
            actor=actor_ctx.actor,
            role=actor_ctx.role,
            approval_id=approval_id,
        )
        return {
            **dto_to_dict(task),
            "risk_tier": "medium",
            "approval_recommended": approval_required("update_task"),
        }

    @mcp.tool(
        name="complete_task",
        description=(
            "Mark a task done. Medium risk: Role.USER callers must pass a valid "
            "approval_id obtained from request_approval(tool_name='complete_task', "
            "arguments={'task_id': id}); Role.ADMIN callers may call this directly "
            "(the bypass is recorded in the audit log)."
        ),
    )
    @handle_tool_errors
    async def complete_task(
        id: str,
        approval_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        task = await tasks_service.complete_task(
            task_id=id, actor=actor_ctx.actor, role=actor_ctx.role, approval_id=approval_id
        )
        return {
            **dto_to_dict(task),
            "risk_tier": "medium",
            "approval_recommended": approval_required("complete_task"),
        }
