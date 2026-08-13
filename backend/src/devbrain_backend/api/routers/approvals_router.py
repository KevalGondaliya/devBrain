"""`GET /approvals/pending` / `POST /approvals/{id}/decide` — thin HTTP
wrappers over `devbrain_common.approvals`, giving a human approving a write
through the eventual frontend UI an HTTP path (previously the only way to
approve was the `decide_approval` MCP tool call, per
`devbrain_common.approval_tools`). Role requirements mirror that MCP tool
surface exactly: `Role.USER` to list pending approvals, `Role.ADMIN` to
decide one.

Requesting a new approval (`request_approval`) has no HTTP endpoint in this
phase — see `chat_router.py`'s module docstring for why: constructing a
write tool's `arguments` dict from an HTTP request body would be exactly
the same "let untrusted input author a write" pattern this whole project
is built to avoid, unless done through a purpose-built proposal function
like `devbrain_backend.agents.safe_write.propose_create_task` (in-process
only, called with real typed keyword arguments, not a JSON grab-bag).
"""

from __future__ import annotations

from devbrain_common.approvals import decide_approval, list_pending_approvals
from devbrain_common.auth import Role
from devbrain_common.db import session_scope
from devbrain_common.mcp_auth import ActorContext
from devbrain_common.models import Approval
from fastapi import APIRouter, Depends

from devbrain_backend.api.auth import require_role
from devbrain_backend.api.schemas import (
    ApprovalDecideRequest,
    ApprovalOut,
    PendingApprovalsResponse,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])

# Module-level singletons, evaluated once at import time — see
# `permissions_router.py`'s identical comment for why (ruff B008).
_require_user = Depends(require_role(Role.USER))
_require_admin = Depends(require_role(Role.ADMIN))


def _approval_out(approval: Approval) -> ApprovalOut:
    return ApprovalOut(
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


@router.get("/pending", response_model=PendingApprovalsResponse)
async def get_pending_approvals(
    _actor_ctx: ActorContext = _require_user,
) -> PendingApprovalsResponse:
    async with session_scope() as session:
        pending = await list_pending_approvals(session)
        return PendingApprovalsResponse(approvals=[_approval_out(a) for a in pending])


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide(
    approval_id: str,
    body: ApprovalDecideRequest,
    actor_ctx: ActorContext = _require_admin,
) -> ApprovalOut:
    async with session_scope() as session:
        approval = await decide_approval(
            session,
            approval_id=approval_id,
            decision=body.decision,
            decided_by=actor_ctx.actor,
            reason=body.reason,
        )
        return _approval_out(approval)
