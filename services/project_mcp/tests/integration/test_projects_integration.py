"""Real `db_test` round-trips against Phase 2's `--size small --seed 42` seed."""

from __future__ import annotations

import uuid

import pytest
from devbrain_common.approvals import decide_approval, request_approval
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, NotFoundError
from project_mcp.services import projects_service
from sqlalchemy.ext.asyncio import AsyncSession


async def test_list_projects_returns_seeded_projects(patched_uow: object) -> None:
    projects = await projects_service.list_projects()
    assert len(projects) >= 1
    assert all(p.id for p in projects)


async def test_search_projects_finds_a_real_project_by_name_fragment(patched_uow: object) -> None:
    projects = await projects_service.list_projects()
    target = projects[0]
    fragment = target.name.split()[0]

    results = await projects_service.search_projects(query=fragment)
    assert any(p.id == target.id for p in results)


async def test_get_project_roundtrip(patched_uow: object) -> None:
    projects = await projects_service.list_projects()
    target = projects[0]

    fetched = await projects_service.get_project(project_id=target.id)
    assert fetched.id == target.id
    assert fetched.name == target.name


async def test_get_project_not_found_raises(patched_uow: object) -> None:
    with pytest.raises(NotFoundError):
        await projects_service.get_project(project_id=str(uuid.uuid4()))


async def test_get_project_status_matches_get_project(patched_uow: object) -> None:
    projects = await projects_service.list_projects()
    target = projects[0]

    status = await projects_service.get_project_status(project_id=target.id)
    assert status.project_id == target.id
    assert status.status == target.status


async def test_update_project_status_persists_and_is_auditable(patched_uow: object) -> None:
    projects = await projects_service.list_projects()
    target = projects[0]
    new_status = "blocked" if target.status != "blocked" else "active"

    updated = await projects_service.update_project_status(
        project_id=target.id,
        status=new_status,
        reason="integration test",
        actor="tester",
        role=Role.ADMIN,
    )
    assert updated.status == new_status

    refetched = await projects_service.get_project(project_id=target.id)
    assert refetched.status == new_status


async def test_update_project_status_user_role_requires_approval_end_to_end(
    patched_uow: AsyncSession,
) -> None:
    """Phase 6 human-in-the-loop gate, full round trip against real
    Postgres: a `Role.USER` call without `approval_id` is rejected; after
    `request_approval` + admin `decide_approval`, retrying with that
    `approval_id` succeeds; retrying a third time with the same id fails
    (already consumed)."""
    projects = await projects_service.list_projects()
    target = projects[0]
    new_status = "blocked" if target.status != "blocked" else "active"

    with pytest.raises(ApprovalRequiredError):
        await projects_service.update_project_status(
            project_id=target.id,
            status=new_status,
            reason="needs approval",
            actor="user-bob",
            role=Role.USER,
        )

    approval = await request_approval(
        patched_uow,
        actor="user-bob",
        tool_name="update_project_status",
        arguments={"project_id": target.id, "status": new_status, "reason": "needs approval"},
    )
    await decide_approval(
        patched_uow, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )

    updated = await projects_service.update_project_status(
        project_id=target.id,
        status=new_status,
        reason="needs approval",
        actor="user-bob",
        role=Role.USER,
        approval_id=str(approval.id),
    )
    assert updated.status == new_status

    with pytest.raises(ApprovalRequiredError):
        await projects_service.update_project_status(
            project_id=target.id,
            status=new_status,
            reason="needs approval",
            actor="user-bob",
            role=Role.USER,
            approval_id=str(approval.id),
        )
