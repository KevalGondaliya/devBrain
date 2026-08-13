"""`GET /activity` — the Tool Execution Viewer's data source
(DevBrain_vision.md §21): recent `audit_logs` rows, newest first, paginated.

No existing service exposes an "audit log listing" read — Phase 1's
`audit_logs` table + Phase 6's `devbrain_common.audit.record_audit_event`
only ever *write* rows, nothing in the codebase before this phase ever
*lists* them back — so this router queries the table directly via
`devbrain_common.db.session_scope()` + the `AuditLog` model, the one place
in Phase 8 that isn't a pure wrapper over an existing function. It's a
single, simple, parameterized `select()` — no raw SQL, matching
ORCHESTRATION.md's rule.
"""

from __future__ import annotations

from devbrain_common.auth import Role
from devbrain_common.db import session_scope
from devbrain_common.mcp_auth import ActorContext
from devbrain_common.models import AuditLog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from devbrain_backend.api.auth import require_role
from devbrain_backend.api.introspection import (
    SHARED_APPROVAL_TOOL_NAMES,
    list_server_tools,
    tool_owner_map,
)
from devbrain_backend.api.schemas import ActivityItem, ActivityResponse

router = APIRouter(tags=["activity"])

# `audit_logs` (Phase 1 schema, `packages/common`) persists only
# `status`/`duration_ms` per call, not a serialized result payload — there
# is no richer "3 tasks" style summary to derive without a schema change
# (out of this phase's read-only-`packages/common` scope, see
# PROGRESS_REPORT.md Phase 8 "Open questions"). This is a deliberately
# honest, minimal summary rather than a fabricated one.
_STATUS_SUMMARY = {
    "success": "completed successfully",
    "error": "failed",
    "denied": "denied (approval/role check failed)",
}


_LIMIT_QUERY = Query(default=50, ge=1, le=200)
_OFFSET_QUERY = Query(default=0, ge=0)
# Module-level singleton, evaluated once at import time — see
# `permissions_router.py`'s identical comment for why (ruff B008).
_require_user = Depends(require_role(Role.USER))


@router.get("/activity", response_model=ActivityResponse)
async def get_activity(
    limit: int = _LIMIT_QUERY,
    offset: int = _OFFSET_QUERY,
    _actor_ctx: ActorContext = _require_user,
) -> ActivityResponse:
    """Role.USER minimum (not Role.VIEWER): unlike a single service's own
    read tools, this exposes call *arguments* and *actor* labels across
    every service at once, which is more operationally sensitive than any
    one read tool's own result."""
    server_tools = await list_server_tools()
    owner = tool_owner_map(server_tools)

    async with session_scope() as session:
        total = (await session.execute(select(func.count()).select_from(AuditLog))).scalar_one()
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()

    items = [
        ActivityItem(
            id=str(row.id),
            server=(
                "shared"
                if row.tool_name in SHARED_APPROVAL_TOOL_NAMES
                else owner.get(row.tool_name, "unknown")
            ),
            tool=row.tool_name,
            arguments=row.arguments,
            result_summary=_STATUS_SUMMARY.get(row.status, row.status),
            status=row.status.upper(),
            latency_ms=row.duration_ms,
            actor=row.actor,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return ActivityResponse(items=items, limit=limit, offset=offset, total=int(total))
