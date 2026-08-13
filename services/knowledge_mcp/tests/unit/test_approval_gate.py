"""Approval-gate coverage for Knowledge MCP's write tools — the gap Phase
8's agent flagged and this change closes (see `risk.py`'s module docstring
and `PROGRESS_REPORT.md`'s Phase 6 addendum). Mirrors `task_mcp`'s
`test_tasks_service.py` "Phase 6: approval gate" section.

Medium-risk (`notes.create`/`notes.update`/`tags.rename`) coverage sticks
to the no-DB guard-clause branches here (a `Role.USER` call with no
`approval_id` raises before any repository call, exactly like
`enforce_approval`'s documented behavior) plus one admin-bypass-is-audited
test. High-risk (`notes.delete`) coverage exercises both of its guard
clauses (non-admin role; admin role but no approval_id) — also both no-DB.
The full request -> admin-decide -> retry round trip against real Postgres
(for both tiers) lives in
`tests/integration/test_approval_gate_integration.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from _fakes import fake_unit_of_work
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, ForbiddenError
from knowledge_mcp.repositories import unit_of_work as uow
from knowledge_mcp.services import notes_service, tags_service


@pytest.fixture(autouse=True)
def _patch_unit_of_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uow, "unit_of_work", fake_unit_of_work)


# --- medium-risk writes: notes.create / notes.update / tags.rename ---------


async def test_create_note_user_without_approval_raises_approval_required() -> None:
    """`enforce_approval` raises before any repository call — no mocking
    needed for this branch."""
    with pytest.raises(ApprovalRequiredError):
        await notes_service.create_note(
            title="Needs approval",
            content_md="body",
            actor="user-bob",
            role=Role.USER,
            approval_id=None,
        )


async def test_update_note_user_without_approval_raises_approval_required() -> None:
    with pytest.raises(ApprovalRequiredError):
        await notes_service.update_note(
            note_id=str(uuid.uuid4()),
            title="x",
            actor="user-bob",
            role=Role.USER,
            approval_id=None,
        )


async def test_rename_tag_user_without_approval_raises_approval_required() -> None:
    with pytest.raises(ApprovalRequiredError):
        await tags_service.rename_tag(
            old_name="old", new_name="new", actor="user-bob", role=Role.USER, approval_id=None
        )


async def test_rename_tag_admin_bypass_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors `task_mcp`'s `test_complete_task_marks_done_and_audits_
    under_its_own_tool_name` for this service: a `Role.ADMIN` caller skips
    the approval requirement entirely, and that bypass is recorded on the
    audit row (`approval_bypassed_by_admin=True`), never silent."""

    @dataclass
    class FakeTag:
        id: uuid.UUID
        name: str

    old_tag = FakeTag(id=uuid.uuid4(), name="oldname")
    recorded: dict[str, object] = {}

    async def fake_get_by_name(session: object, name: str) -> FakeTag | None:
        return old_tag if name.strip().lower() == "oldname" else None

    def fake_rename(tag: FakeTag, new_name: str) -> None:
        tag.name = new_name

    async def fake_list_all_with_counts(session: object) -> list[tuple[FakeTag, int]]:
        return [(old_tag, 1)]

    async def fake_record_audit_event(session: object, **kwargs: object) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr(tags_service.tags_repository, "get_by_name", fake_get_by_name)
    monkeypatch.setattr(tags_service.tags_repository, "rename", fake_rename)
    monkeypatch.setattr(
        tags_service.tags_repository, "list_all_with_counts", fake_list_all_with_counts
    )
    monkeypatch.setattr(tags_service, "record_audit_event", fake_record_audit_event)

    result = await tags_service.rename_tag(
        old_name="oldname", new_name="newname", actor="admin-alice", role=Role.ADMIN
    )

    assert result.name == "newname"
    arguments = recorded["arguments"]
    assert isinstance(arguments, dict)
    assert arguments["approval_bypassed_by_admin"] is True
    assert arguments["approval_id"] is None


# --- high-risk write: notes.delete (admin AND approval, not either/or) -----


async def test_delete_note_user_role_raises_forbidden_even_without_approval() -> None:
    """`Role.USER` is rejected outright — high risk requires `Role.ADMIN`;
    no `approval_id` can substitute for it."""
    with pytest.raises(ForbiddenError):
        await notes_service.delete_note(
            note_id=str(uuid.uuid4()), actor="user-bob", role=Role.USER, approval_id=None
        )


async def test_delete_note_viewer_role_raises_forbidden() -> None:
    with pytest.raises(ForbiddenError):
        await notes_service.delete_note(
            note_id=str(uuid.uuid4()), actor="viewer-vic", role=Role.VIEWER, approval_id=None
        )


async def test_delete_note_admin_without_approval_raises_approval_required() -> None:
    """`Role.ADMIN` is necessary but not sufficient — high risk still needs
    a valid `approval_id`, unlike every medium-risk write in this project
    (where admin alone bypasses)."""
    with pytest.raises(ApprovalRequiredError):
        await notes_service.delete_note(
            note_id=str(uuid.uuid4()), actor="admin-alice", role=Role.ADMIN, approval_id=None
        )
