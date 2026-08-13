"""Real `db_test` round trips for the approval gate closed post-Phase-6 (see
`risk.py`'s module docstring and `PROGRESS_REPORT.md`'s Phase 6 addendum).
Mirrors `project_mcp`'s
`test_update_project_status_user_role_requires_approval_end_to_end`, plus a
`notes.delete`-specific test proving the high-risk tier's stricter "admin
AND approval, not either/or" gate.
"""

from __future__ import annotations

import pytest
from devbrain_common.approvals import decide_approval, request_approval
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, ForbiddenError, NotFoundError
from devbrain_common.models import AuditLog
from knowledge_mcp.services import notes_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("patched_uow")


async def test_notes_create_user_role_requires_approval_end_to_end(
    patched_uow: AsyncSession,
) -> None:
    """A `Role.USER` call without `approval_id` is rejected; after
    `request_approval` + admin `decide_approval`, retrying with that
    `approval_id` succeeds; retrying a third time with the same id fails
    (already consumed)."""
    arguments = {
        "title": "User-requested note",
        "content_md": "body",
        "tags": [],
        "project_id": None,
        "note_type": "technical",
    }

    with pytest.raises(ApprovalRequiredError):
        await notes_service.create_note(
            title="User-requested note",
            content_md="body",
            actor="user-bob",
            role=Role.USER,
        )

    approval = await request_approval(
        patched_uow, actor="user-bob", tool_name="notes.create", arguments=arguments
    )
    await decide_approval(
        patched_uow, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    created = await notes_service.create_note(
        title="User-requested note",
        content_md="body",
        actor="user-bob",
        role=Role.USER,
        approval_id=str(approval.id),
    )
    assert created.title == "User-requested note"

    with pytest.raises(ApprovalRequiredError):
        await notes_service.create_note(
            title="User-requested note",
            content_md="body",
            actor="user-bob",
            role=Role.USER,
            approval_id=str(approval.id),
        )


async def test_notes_create_admin_bypass_succeeds_and_is_audited(
    patched_uow: AsyncSession,
) -> None:
    created = await notes_service.create_note(
        title="Admin-bypass note",
        content_md="body",
        actor="admin-alice",
        role=Role.ADMIN,
    )
    assert created.title == "Admin-bypass note"

    rows = await patched_uow.execute(select(AuditLog).where(AuditLog.tool_name == "notes.create"))
    matching = [r for r in rows.scalars() if r.arguments.get("title") == "Admin-bypass note"]
    assert len(matching) == 1
    assert matching[0].arguments["approval_bypassed_by_admin"] is True
    assert matching[0].arguments["approval_id"] is None


async def test_notes_delete_requires_both_admin_and_approval_end_to_end(
    patched_uow: AsyncSession,
) -> None:
    """`notes.delete` is high-risk: `Role.ADMIN` alone does not bypass
    approval (unlike medium risk), and `Role.USER` is rejected outright even
    with a valid, approved `approval_id` — both must hold at once."""
    note = await notes_service.create_note(
        title="Note to delete",
        content_md="body",
        actor="admin-alice",
        role=Role.ADMIN,
    )

    approval = await request_approval(
        patched_uow,
        actor="admin-alice",
        tool_name="notes.delete",
        arguments={"note_id": note.id},
        risk_tier="high",
    )
    await decide_approval(
        patched_uow, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    # Role.USER can't use this approval no matter what — high risk is
    # admin-only, full stop.
    with pytest.raises(ForbiddenError):
        await notes_service.delete_note(
            note_id=note.id, actor="user-bob", role=Role.USER, approval_id=str(approval.id)
        )

    # Role.ADMIN without the approval_id is rejected too.
    with pytest.raises(ApprovalRequiredError):
        await notes_service.delete_note(note_id=note.id, actor="admin-alice", role=Role.ADMIN)

    # Both together succeed.
    await notes_service.delete_note(
        note_id=note.id, actor="admin-alice", role=Role.ADMIN, approval_id=str(approval.id)
    )

    # Soft-deleted (default `get_note` excludes deleted notes, same as the
    # plain CRUD round-trip test).
    with pytest.raises(NotFoundError):
        await notes_service.get_note(note_id=note.id)

    # The approval was consumed — reusing it fails even for a fresh delete.
    with pytest.raises(ApprovalRequiredError):
        await notes_service.delete_note(
            note_id=note.id, actor="admin-alice", role=Role.ADMIN, approval_id=str(approval.id)
        )
