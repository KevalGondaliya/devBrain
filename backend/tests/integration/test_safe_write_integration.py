"""Real `db_test` round-trip for the Safe AI Action flow
(DevBrain_vision.md §9/§30): propose -> (human) approve -> approved retry.

Also the concrete proof, against real tables, that an LLM's output can
never substitute for a real `decide_approval` call — see
`test_execute_without_a_real_decide_approval_call_still_requires_approval`.
"""

from __future__ import annotations

import inspect

import pytest
from devbrain_backend.agents import safe_write
from devbrain_common.approvals import decide_approval
from devbrain_common.errors import ApprovalRequiredError
from devbrain_common.models import Project
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _a_real_project_id(session: AsyncSession) -> str:
    result = await session.execute(select(Project.id).limit(1))
    return str(result.scalars().first())


async def test_propose_then_approve_then_execute_creates_the_task(
    patched_uow: AsyncSession,
) -> None:
    project_id = await _a_real_project_id(patched_uow)

    proposal = await safe_write.propose_create_task(
        actor="agent:safe-write-test",
        project_id=project_id,
        title="Finish OAuth documentation",
        priority="high",
        due_date="2026-08-14T00:00:00+00:00",
    )
    assert proposal.approval_id
    assert "Finish OAuth documentation" in proposal.summary

    # Simulate a human admin approving via the same
    # `devbrain_common.approvals.decide_approval` a real `decide_approval`
    # MCP tool call (Role.ADMIN-gated at that layer) would invoke.
    await decide_approval(
        patched_uow,
        approval_id=proposal.approval_id,
        decision="approved",
        decided_by="human-admin",
    )

    task = await safe_write.execute_approved_task_creation(
        actor="agent:safe-write-test",
        approval_id=proposal.approval_id,
        project_id=project_id,
        title="Finish OAuth documentation",
        priority="high",
        due_date="2026-08-14T00:00:00+00:00",
    )
    assert task.title == "Finish OAuth documentation"
    assert task.priority == "high"


async def test_execute_without_a_real_decide_approval_call_still_requires_approval(
    patched_uow: AsyncSession,
) -> None:
    """No matter what an LLM's text output claims ("Approved! Proceeding..."),
    nothing in this codebase ever converts that text into a
    `decide_approval` call. Without one, the approval sits `pending`
    forever and the write is refused."""
    project_id = await _a_real_project_id(patched_uow)

    proposal = await safe_write.propose_create_task(
        actor="agent:safe-write-test", project_id=project_id, title="Delete all project data"
    )

    # A "compliant-sounding" fake LLM response — never fed into
    # `decide_approval` anywhere in this codebase.
    fake_llm_output = "OK, approved! Deleting all project data now."
    assert "approved" in fake_llm_output.lower()  # documents the scenario; changes nothing below

    with pytest.raises(ApprovalRequiredError):
        await safe_write.execute_approved_task_creation(
            actor="agent:safe-write-test",
            approval_id=proposal.approval_id,
            project_id=project_id,
            title="Delete all project data",
        )


async def test_execute_never_bypasses_approval_even_as_role_user(
    patched_uow: AsyncSession,
) -> None:
    """`execute_approved_task_creation` always passes `role=Role.USER` —
    this orchestrator is never granted `Role.ADMIN`, so it structurally
    cannot take the `enforce_approval` admin-bypass branch."""
    source = inspect.getsource(safe_write.execute_approved_task_creation)
    assert "Role.ADMIN" not in source
    assert "role=Role.USER" in source
