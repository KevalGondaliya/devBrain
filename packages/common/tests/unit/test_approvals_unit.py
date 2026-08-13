"""`devbrain_common.approvals.enforce_approval` — the two branches that
never touch the database (admin bypass; user with no `approval_id` at
all). The full consume/decide/mismatch round trip needs a real `approvals`
row and is covered by
`packages/common/tests/integration/test_approvals_integration.py`.
"""

from __future__ import annotations

import pytest
from devbrain_common.approvals import enforce_approval
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError


async def test_admin_bypasses_without_touching_session() -> None:
    bypassed = await enforce_approval(
        None,  # type: ignore[arg-type] # never dereferenced on this branch
        role=Role.ADMIN,
        actor="admin-alice",
        tool_name="create_task",
        arguments={"title": "x"},
        approval_id=None,
    )
    assert bypassed is True


async def test_user_without_approval_id_raises_approval_required() -> None:
    with pytest.raises(ApprovalRequiredError) as exc_info:
        await enforce_approval(
            None,  # type: ignore[arg-type]
            role=Role.USER,
            actor="user-bob",
            tool_name="create_task",
            arguments={"title": "x"},
            approval_id=None,
        )
    assert exc_info.value.code == "approval_required"
    assert exc_info.value.http_status == 403


async def test_user_with_blank_approval_id_raises_approval_required() -> None:
    with pytest.raises(ApprovalRequiredError):
        await enforce_approval(
            None,  # type: ignore[arg-type]
            role=Role.USER,
            actor="user-bob",
            tool_name="create_task",
            arguments={"title": "x"},
            approval_id="",
        )


async def test_viewer_without_approval_id_raises_approval_required() -> None:
    """Viewer role never actually reaches this gate in practice (`require_min_role`
    already blocks viewers from write tools before `enforce_approval` runs),
    but the function itself doesn't special-case viewer vs. user — anything
    below admin needs an approval."""
    with pytest.raises(ApprovalRequiredError):
        await enforce_approval(
            None,  # type: ignore[arg-type]
            role=Role.VIEWER,
            actor="viewer-carol",
            tool_name="create_task",
            arguments={"title": "x"},
            approval_id=None,
        )
