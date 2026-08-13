"""Human-in-the-loop approval gate (DevBrain_vision.md §9/§10), backed by
the `approvals` table that has existed since Phase 1 but nothing used until
now.

Full design — see PROGRESS_REPORT.md Phase 6 "Decisions made" for the
authoritative writeup, this is the short version:

- `request_approval` inserts a `pending` row for one exact
  `tool_name` + `arguments` call.
- `decide_approval` (admin-only — enforced by the *caller*, e.g.
  `devbrain_common.approval_tools.register_approval_tools`, via
  `require_min_role(ctx, Role.ADMIN)`, not by this function itself) flips a
  pending row to `approved`/`rejected`.
- `consume_approval` is the one-shot spend: marks an `approved` row's
  `consumed_at`, raising `ApprovalRequiredError` for absolutely any reason
  it can't be spent (not found, wrong tool/arguments, not approved, already
  consumed) — deliberately one error type, since from the retrying tool
  call's point of view every failure mode means the same thing: *you don't
  have a valid, unused approval for this exact call*.
- `enforce_approval` is what every medium+ risk write tool actually calls:
  `Role.ADMIN` callers bypass immediately (returns `True` — the caller must
  then stamp `approval_bypassed_by_admin=true` on its audit-log row, so the
  bypass itself stays visible); `Role.USER` callers must supply a valid
  `approval_id`, checked via `consume_approval`, or the call raises
  `ApprovalRequiredError` (mapped to a 403-shaped structured error, code
  `APPROVAL_REQUIRED`) before anything is mutated.

`arguments` dicts must already be JSON-safe (str/int/float/bool/None/list/
dict only — no raw `UUID`/`datetime` objects) since they round-trip through
Postgres JSONB and are compared with plain `==` in `consume_approval`: a
call approved for one set of arguments must not be usable to execute a
different one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devbrain_common.auth import Role
from devbrain_common.errors import (
    ApprovalRequiredError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from devbrain_common.models import Approval

_DECISIONS = ("approved", "rejected")


async def request_approval(
    session: AsyncSession,
    *,
    actor: str,
    tool_name: str,
    arguments: dict[str, Any],
    risk_tier: str = "medium",
) -> Approval:
    """Create a `pending` approval row for one exact `tool_name` +
    `arguments` call."""
    approval = Approval(
        id=uuid.uuid4(),
        tool_name=tool_name,
        arguments=arguments,
        actor=actor,
        risk_tier=risk_tier,
        status="pending",
    )
    session.add(approval)
    await session.flush()
    return approval


async def list_pending_approvals(session: AsyncSession, *, limit: int = 50) -> list[Approval]:
    """Oldest-first list of `pending` approvals, for whoever's reviewing."""
    stmt = (
        select(Approval)
        .where(Approval.status == "pending")
        .order_by(Approval.requested_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _get_approval(session: AsyncSession, approval_id: str) -> Approval:
    try:
        parsed_id = uuid.UUID(approval_id)
    except ValueError as exc:
        raise NotFoundError(f"{approval_id!r} is not a valid approval id.") from exc
    approval = await session.get(Approval, parsed_id)
    if approval is None:
        raise NotFoundError(f"No approval found with id {approval_id!r}.")
    return approval


async def decide_approval(
    session: AsyncSession,
    *,
    approval_id: str,
    decision: str,
    decided_by: str,
    reason: str | None = None,
) -> Approval:
    """Approve or reject a `pending` approval.

    Admin-only in practice, but that's enforced by the *caller* (the MCP
    tool wrapper calls `require_min_role(ctx, Role.ADMIN)` before this ever
    runs) — this function itself is role-agnostic so it stays trivially
    unit-testable without an MCP context. Raises `NotFoundError` for a
    missing/malformed id, `ValidationError` for a bad `decision` value,
    `ConflictError` if the approval isn't `pending` anymore.
    """
    if decision not in _DECISIONS:
        raise ValidationError(f"decision must be one of {_DECISIONS}.")
    approval = await _get_approval(session, approval_id)
    if approval.status != "pending":
        raise ConflictError(f"Approval {approval_id!r} was already {approval.status!r}.")

    approval.status = decision
    approval.decided_at = datetime.now(UTC)
    approval.decided_by = decided_by
    approval.reason = reason
    await session.flush()
    return approval


async def consume_approval(
    session: AsyncSession,
    *,
    approval_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> None:
    """Spend an `approved` approval for exactly this `tool_name` +
    `arguments` call. Raises `ApprovalRequiredError` if the id is
    malformed/missing, the tool/arguments don't match exactly, the
    approval isn't `approved`, or it was already consumed once before —
    every failure mode collapses to the same actionable error for the
    caller: *request a fresh approval and retry*.
    """
    try:
        parsed_id = uuid.UUID(approval_id)
    except ValueError as exc:
        raise ApprovalRequiredError(f"{approval_id!r} is not a valid approval id.") from exc

    approval = await session.get(Approval, parsed_id)
    if approval is None:
        raise ApprovalRequiredError(f"No approval found with id {approval_id!r}.")
    if approval.tool_name != tool_name or approval.arguments != arguments:
        raise ApprovalRequiredError(
            "Approval does not match this tool call's name/arguments exactly."
        )
    if approval.status != "approved":
        raise ApprovalRequiredError(
            f"Approval {approval_id!r} is not approved (status={approval.status!r})."
        )
    if approval.consumed_at is not None:
        raise ApprovalRequiredError(f"Approval {approval_id!r} was already used.")

    approval.consumed_at = datetime.now(UTC)
    await session.flush()


async def enforce_approval(
    session: AsyncSession,
    *,
    role: Role,
    actor: str,
    tool_name: str,
    arguments: dict[str, Any],
    approval_id: str | None,
) -> bool:
    """The gate every medium+ risk write tool's service function calls
    right before mutating anything.

    Returns `True` if this call bypassed approval as an admin (the caller
    must then record `approval_bypassed_by_admin=true` on its audit-log
    row), `False` if a valid approval was consumed instead. Raises
    `ApprovalRequiredError` for a non-admin caller with no (or an invalid)
    `approval_id` — nothing is mutated when this raises, since every
    service function calls this before its write.
    """
    if role.at_least(Role.ADMIN):
        return True
    if not approval_id:
        raise ApprovalRequiredError(
            f"Tool {tool_name!r} requires approval before it can execute as role "
            f"{role.value!r}. Call request_approval with the exact same arguments first."
        )
    await consume_approval(
        session, approval_id=approval_id, tool_name=tool_name, arguments=arguments
    )
    return False
