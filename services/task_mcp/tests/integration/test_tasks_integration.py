"""Real `db_test` round-trips against Phase 2's `--size small --seed 42` seed."""

from __future__ import annotations

import uuid

import pytest
from devbrain_common.approvals import decide_approval, request_approval
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, NotFoundError, ValidationError
from devbrain_common.models import Project, Task
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from task_mcp.services import tasks_service


async def _a_real_project_id(db_session: AsyncSession) -> str:
    result = await db_session.execute(select(Project.id).limit(1))
    project_id = result.scalar_one()
    return str(project_id)


async def test_list_tasks_returns_seeded_tasks(patched_uow: AsyncSession) -> None:
    tasks = await tasks_service.list_tasks()
    assert len(tasks) >= 1


async def test_list_tasks_filters_by_project(patched_uow: AsyncSession) -> None:
    project_id = await _a_real_project_id(patched_uow)
    tasks = await tasks_service.list_tasks(project_id=project_id)
    assert all(t.project_id == project_id for t in tasks)


async def test_search_tasks_finds_a_real_task_by_title_fragment(patched_uow: AsyncSession) -> None:
    all_tasks = await tasks_service.list_tasks()
    target = all_tasks[0]
    fragment = target.title.split()[0]

    results = await tasks_service.search_tasks(query=fragment)
    assert any(t.id == target.id for t in results)


async def test_get_task_roundtrip(patched_uow: AsyncSession) -> None:
    all_tasks = await tasks_service.list_tasks()
    target = all_tasks[0]

    fetched = await tasks_service.get_task(task_id=target.id)
    assert fetched.id == target.id
    assert fetched.title == target.title


async def test_get_task_not_found_raises(patched_uow: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await tasks_service.get_task(task_id=str(uuid.uuid4()))


async def test_create_task_persists_against_real_project(patched_uow: AsyncSession) -> None:
    project_id = await _a_real_project_id(patched_uow)

    created = await tasks_service.create_task(
        project_id=project_id,
        title="Integration-created task",
        description="from the integration suite",
        priority="high",
        actor="tester",
        role=Role.ADMIN,
    )
    assert created.status == "todo"

    refetched = await tasks_service.get_task(task_id=created.id)
    assert refetched.title == "Integration-created task"
    assert refetched.project_id == project_id


async def test_create_task_unknown_project_raises_not_found(patched_uow: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await tasks_service.create_task(
            project_id=str(uuid.uuid4()), title="Orphan task", actor="tester", role=Role.ADMIN
        )


async def test_create_task_idempotency_key_prevents_duplicate(patched_uow: AsyncSession) -> None:
    project_id = await _a_real_project_id(patched_uow)
    key = f"integration-test-{uuid.uuid4()}"

    first = await tasks_service.create_task(
        project_id=project_id,
        title="Idempotent task",
        idempotency_key=key,
        actor="tester",
        role=Role.ADMIN,
    )
    second = await tasks_service.create_task(
        project_id=project_id,
        title="Idempotent task",
        idempotency_key=key,
        actor="tester",
        role=Role.ADMIN,
    )

    assert first.id == second.id

    count_result = await patched_uow.execute(
        select(func.count()).select_from(Task).where(Task.title == "Idempotent task")
    )
    assert count_result.scalar_one() == 1


async def test_update_task_persists_status_change(patched_uow: AsyncSession) -> None:
    all_tasks = await tasks_service.list_tasks()
    target = next(t for t in all_tasks if t.status != "blocked")

    updated = await tasks_service.update_task(
        task_id=target.id,
        status="blocked",
        blocked_reason="integration test",
        actor="tester",
        role=Role.ADMIN,
    )
    assert updated.status == "blocked"
    assert updated.blocked_reason == "integration test"

    refetched = await tasks_service.get_task(task_id=target.id)
    assert refetched.status == "blocked"


async def test_update_task_blocked_without_reason_raises(patched_uow: AsyncSession) -> None:
    all_tasks = await tasks_service.list_tasks()
    target = next(t for t in all_tasks if t.status != "blocked")

    with pytest.raises(ValidationError):
        await tasks_service.update_task(
            task_id=target.id, status="blocked", actor="tester", role=Role.ADMIN
        )


async def test_complete_task_marks_done(patched_uow: AsyncSession) -> None:
    all_tasks = await tasks_service.list_tasks()
    target = next(t for t in all_tasks if t.status != "done")

    completed = await tasks_service.complete_task(
        task_id=target.id, actor="tester", role=Role.ADMIN
    )
    assert completed.status == "done"

    refetched = await tasks_service.get_task(task_id=target.id)
    assert refetched.status == "done"


async def test_create_task_user_role_requires_approval_end_to_end(
    patched_uow: AsyncSession,
) -> None:
    """Phase 6 human-in-the-loop gate, full round trip against real
    Postgres: a `Role.USER` call without `approval_id` is rejected; after
    `request_approval` + admin `decide_approval`, retrying with that
    `approval_id` succeeds; retrying a third time with the same id fails
    (already consumed)."""
    project_id = await _a_real_project_id(patched_uow)
    call_arguments = {
        "project_id": project_id,
        "title": "Needs sign-off",
        "description": None,
        "priority": None,
        "assignee": None,
        "due_date": None,
    }

    with pytest.raises(ApprovalRequiredError):
        await tasks_service.create_task(
            project_id=project_id, title="Needs sign-off", actor="user-bob", role=Role.USER
        )

    approval = await request_approval(
        patched_uow, actor="user-bob", tool_name="create_task", arguments=call_arguments
    )
    await decide_approval(
        patched_uow, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    created = await tasks_service.create_task(
        project_id=project_id,
        title="Needs sign-off",
        actor="user-bob",
        role=Role.USER,
        approval_id=str(approval.id),
    )
    assert created.title == "Needs sign-off"

    with pytest.raises(ApprovalRequiredError):
        await tasks_service.create_task(
            project_id=project_id,
            title="Needs sign-off",
            actor="user-bob",
            role=Role.USER,
            approval_id=str(approval.id),
        )
