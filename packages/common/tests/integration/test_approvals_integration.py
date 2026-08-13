"""`devbrain_common.approvals` full round trip against real Postgres
(`db_test`) — the branches `test_approvals_unit.py` can't cover without a
real `approvals` row: consuming an approval, decision state transitions,
and the argument-mismatch/already-consumed/not-approved-yet failure modes.
"""

from __future__ import annotations

import uuid

import pytest
from devbrain_common.approvals import (
    consume_approval,
    decide_approval,
    enforce_approval,
    list_pending_approvals,
    request_approval,
)
from devbrain_common.auth import Role
from devbrain_common.errors import (
    ApprovalRequiredError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from sqlalchemy.ext.asyncio import AsyncSession


async def test_request_approval_creates_pending_row_visible_in_listing(
    db_session: AsyncSession,
) -> None:
    approval = await request_approval(
        db_session,
        actor="user-bob",
        tool_name="create_task",
        arguments={"project_id": "p1", "title": "Ship it"},
    )
    assert approval.status == "pending"
    assert approval.risk_tier == "medium"
    assert approval.consumed_at is None

    pending = await list_pending_approvals(db_session)
    assert any(a.id == approval.id for a in pending)


async def test_decide_approval_approves(db_session: AsyncSession) -> None:
    approval = await request_approval(
        db_session,
        actor="user-bob",
        tool_name="create_task",
        arguments={"title": "x"},
    )
    decided = await decide_approval(
        db_session, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )
    assert decided.status == "approved"
    assert decided.decided_by == "admin-alice"
    assert decided.decided_at is not None

    pending = await list_pending_approvals(db_session)
    assert all(a.id != approval.id for a in pending)


async def test_decide_approval_rejects(db_session: AsyncSession) -> None:
    approval = await request_approval(
        db_session, actor="user-bob", tool_name="create_task", arguments={"title": "x"}
    )
    decided = await decide_approval(
        db_session,
        approval_id=str(approval.id),
        decision="rejected",
        decided_by="admin-alice",
        reason="not now",
    )
    assert decided.status == "rejected"
    assert decided.reason == "not now"


async def test_decide_approval_twice_raises_conflict(db_session: AsyncSession) -> None:
    approval = await request_approval(
        db_session, actor="user-bob", tool_name="create_task", arguments={"title": "x"}
    )
    await decide_approval(
        db_session, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )
    with pytest.raises(ConflictError):
        await decide_approval(
            db_session,
            approval_id=str(approval.id),
            decision="rejected",
            decided_by="admin-alice",
        )


async def test_decide_approval_rejects_invalid_decision_value(db_session: AsyncSession) -> None:
    approval = await request_approval(
        db_session, actor="user-bob", tool_name="create_task", arguments={"title": "x"}
    )
    with pytest.raises(ValidationError):
        await decide_approval(
            db_session, approval_id=str(approval.id), decision="maybe", decided_by="admin-alice"
        )


async def test_decide_approval_missing_id_raises_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await decide_approval(
            db_session,
            approval_id=str(uuid.uuid4()),
            decision="approved",
            decided_by="admin-alice",
        )


async def test_consume_approval_succeeds_once_then_fails_on_replay(
    db_session: AsyncSession,
) -> None:
    arguments = {"project_id": "p1", "title": "Ship it"}
    approval = await request_approval(
        db_session, actor="user-bob", tool_name="create_task", arguments=arguments
    )
    await decide_approval(
        db_session, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    await consume_approval(
        db_session, approval_id=str(approval.id), tool_name="create_task", arguments=arguments
    )

    with pytest.raises(ApprovalRequiredError):
        await consume_approval(
            db_session, approval_id=str(approval.id), tool_name="create_task", arguments=arguments
        )


async def test_consume_approval_raises_for_mismatched_arguments(db_session: AsyncSession) -> None:
    approval = await request_approval(
        db_session,
        actor="user-bob",
        tool_name="create_task",
        arguments={"project_id": "p1", "title": "Ship it"},
    )
    await decide_approval(
        db_session, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    with pytest.raises(ApprovalRequiredError):
        await consume_approval(
            db_session,
            approval_id=str(approval.id),
            tool_name="create_task",
            arguments={"project_id": "p1", "title": "A totally different task"},
        )


async def test_consume_approval_raises_for_mismatched_tool_name(db_session: AsyncSession) -> None:
    approval = await request_approval(
        db_session, actor="user-bob", tool_name="create_task", arguments={"title": "x"}
    )
    await decide_approval(
        db_session, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    with pytest.raises(ApprovalRequiredError):
        await consume_approval(
            db_session,
            approval_id=str(approval.id),
            tool_name="update_task",
            arguments={"title": "x"},
        )


async def test_consume_approval_raises_when_still_pending(db_session: AsyncSession) -> None:
    approval = await request_approval(
        db_session, actor="user-bob", tool_name="create_task", arguments={"title": "x"}
    )
    with pytest.raises(ApprovalRequiredError):
        await consume_approval(
            db_session,
            approval_id=str(approval.id),
            tool_name="create_task",
            arguments={"title": "x"},
        )


async def test_consume_approval_raises_when_rejected(db_session: AsyncSession) -> None:
    approval = await request_approval(
        db_session, actor="user-bob", tool_name="create_task", arguments={"title": "x"}
    )
    await decide_approval(
        db_session, approval_id=str(approval.id), decision="rejected", decided_by="admin-alice"
    )
    with pytest.raises(ApprovalRequiredError):
        await consume_approval(
            db_session,
            approval_id=str(approval.id),
            tool_name="create_task",
            arguments={"title": "x"},
        )


async def test_consume_approval_raises_for_unknown_id(db_session: AsyncSession) -> None:
    with pytest.raises(ApprovalRequiredError):
        await consume_approval(
            db_session,
            approval_id=str(uuid.uuid4()),
            tool_name="create_task",
            arguments={"title": "x"},
        )


async def test_consume_approval_raises_for_malformed_id(db_session: AsyncSession) -> None:
    with pytest.raises(ApprovalRequiredError):
        await consume_approval(
            db_session, approval_id="not-a-uuid", tool_name="create_task", arguments={"title": "x"}
        )


async def test_enforce_approval_end_to_end_request_approve_then_succeed(
    db_session: AsyncSession,
) -> None:
    """The exact sequence a `Role.USER` caller goes through: call without
    approval -> APPROVAL_REQUIRED, request + admin-approve, retry with the
    approval_id -> succeeds (and is consumed, so a second retry fails)."""
    arguments = {"project_id": "p1", "title": "Ship it"}

    with pytest.raises(ApprovalRequiredError):
        await enforce_approval(
            db_session,
            role=Role.USER,
            actor="user-bob",
            tool_name="create_task",
            arguments=arguments,
            approval_id=None,
        )

    approval = await request_approval(
        db_session, actor="user-bob", tool_name="create_task", arguments=arguments
    )
    await decide_approval(
        db_session, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    bypassed = await enforce_approval(
        db_session,
        role=Role.USER,
        actor="user-bob",
        tool_name="create_task",
        arguments=arguments,
        approval_id=str(approval.id),
    )
    assert bypassed is False

    with pytest.raises(ApprovalRequiredError):
        await enforce_approval(
            db_session,
            role=Role.USER,
            actor="user-bob",
            tool_name="create_task",
            arguments=arguments,
            approval_id=str(approval.id),
        )


async def test_enforce_approval_admin_bypasses_without_any_approval_row(
    db_session: AsyncSession,
) -> None:
    bypassed = await enforce_approval(
        db_session,
        role=Role.ADMIN,
        actor="admin-alice",
        tool_name="create_task",
        arguments={"title": "x"},
        approval_id=None,
    )
    assert bypassed is True
