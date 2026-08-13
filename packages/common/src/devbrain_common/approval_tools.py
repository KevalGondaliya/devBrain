"""MCP tool registrations for the approval gate (`devbrain_common.approvals`).

Registered once here and mounted on every service's `server.py` (Phase 6)
via `register_approval_tools(mcp, unit_of_work=..., require_min_role=...)`
— any of the five DevBrain MCP servers can be used to request/review/decide
a pending approval, rather than building a separate sixth "approvals"
server just to host three tools.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# NOT under `TYPE_CHECKING` — despite `from __future__ import annotations`
# making every annotation a lazily-evaluated string, FastMCP's own
# `@mcp.tool()` decorator introspects each wrapped function's *live*
# `__annotations__`/`__globals__` at registration time (via
# `mcp.server.fastmcp.utilities.func_metadata.func_metadata`) to build the
# client-visible tool schema — so `Context`/`FastMCP` must actually be
# resolvable names in this module's namespace at import time, exactly like
# every service's own `tools/*.py`. A `TYPE_CHECKING`-only import here
# passed mypy but broke every server at *runtime* the first time
# `create_server()` actually ran (caught via a real `list_tools()` smoke
# test, not by the test suite — see PROGRESS_REPORT.md Phase 6).
from mcp.server.fastmcp import Context, FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from devbrain_common import approvals as _approvals
from devbrain_common.auth import Role
from devbrain_common.mcp_auth import RequireMinRole
from devbrain_common.mcp_tooling import dto_to_dict, handle_tool_errors
from devbrain_common.models import Approval

UnitOfWork = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class ApprovalDTO:
    id: str
    tool_name: str
    arguments: dict[str, Any]
    actor: str
    risk_tier: str
    status: str
    requested_at: datetime | None
    decided_at: datetime | None
    decided_by: str | None
    reason: str | None
    consumed_at: datetime | None


def _to_dto(approval: Approval) -> ApprovalDTO:
    return ApprovalDTO(
        id=str(approval.id),
        tool_name=approval.tool_name,
        arguments=approval.arguments,
        actor=approval.actor,
        risk_tier=approval.risk_tier,
        status=approval.status,
        requested_at=approval.requested_at,
        decided_at=approval.decided_at,
        decided_by=approval.decided_by,
        reason=approval.reason,
        consumed_at=approval.consumed_at,
    )


def register_approval_tools(
    mcp: FastMCP,
    *,
    unit_of_work: UnitOfWork,
    require_min_role: RequireMinRole,
) -> None:
    """Register `request_approval` / `list_pending_approvals` /
    `decide_approval` on `mcp`.

    `request_approval`/`list_pending_approvals` require `Role.USER`;
    `decide_approval` requires `Role.ADMIN` — enforced here via
    `require_min_role`, not left to `devbrain_common.approvals
    .decide_approval` itself (which is role-agnostic on purpose, see its
    docstring).
    """

    @mcp.tool(
        name="request_approval",
        description=(
            "Request human approval for a medium/high-risk tool call before executing it. "
            "Pass the exact tool_name and arguments you intend to call next — the returned "
            "approval_id only unlocks that exact tool_name+arguments combination."
        ),
    )
    @handle_tool_errors
    async def request_approval(
        tool_name: str,
        arguments: dict[str, Any],
        risk_tier: str = "medium",
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.USER)
        async with unit_of_work() as session:
            approval = await _approvals.request_approval(
                session,
                actor=actor_ctx.actor,
                tool_name=tool_name,
                arguments=arguments,
                risk_tier=risk_tier,
            )
            return dto_to_dict(_to_dto(approval))

    @mcp.tool(
        name="list_pending_approvals",
        description="List approval requests still awaiting a decision, oldest first.",
    )
    @handle_tool_errors
    async def list_pending_approvals(
        limit: int = 50,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.USER)
        async with unit_of_work() as session:
            pending = await _approvals.list_pending_approvals(session, limit=limit)
            return {"approvals": [dto_to_dict(_to_dto(a)) for a in pending]}

    @mcp.tool(
        name="decide_approval",
        description=(
            "Approve or reject a pending approval request. Admin only. "
            "decision must be 'approved' or 'rejected'."
        ),
    )
    @handle_tool_errors
    async def decide_approval(
        approval_id: str,
        decision: str,
        reason: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        actor_ctx = require_min_role(ctx, Role.ADMIN)
        async with unit_of_work() as session:
            approval = await _approvals.decide_approval(
                session,
                approval_id=approval_id,
                decision=decision,
                decided_by=actor_ctx.actor,
                reason=reason,
            )
            return dto_to_dict(_to_dto(approval))


__all__ = ["ApprovalDTO", "RequireMinRole", "UnitOfWork", "register_approval_tools"]
