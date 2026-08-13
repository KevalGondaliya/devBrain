"""`GET /approvals/pending` + `POST /approvals/{id}/decide` — the
request -> list -> decide-via-HTTP -> underlying write actually usable
round trip (mirrors `backend/tests/integration/test_safe_write_integration.py`,
just decided through the HTTP endpoint instead of a direct
`decide_approval` call).

Requesting the approval itself has no HTTP endpoint in this phase (see
`chat_router.py`'s module docstring) — done here via
`devbrain_common.approvals.request_approval` directly, exactly like a real
orchestrator (e.g. `devbrain_backend.agents.safe_write.propose_create_task`)
would.
"""

from __future__ import annotations

import asyncio

from devbrain_common.approvals import request_approval
from devbrain_common.auth import Role
from devbrain_common.db import session_scope
from devbrain_common.errors import ApprovalRequiredError
from fastapi.testclient import TestClient
from project_mcp.services import projects_service

from conftest import ADMIN_TOKEN, USER_TOKEN, VIEWER_TOKEN


async def _request_status_change_approval() -> tuple[str, str]:
    projects = await projects_service.list_projects()
    project = projects[0]
    async with session_scope() as session:
        approval = await request_approval(
            session,
            actor="tester",
            tool_name="update_project_status",
            arguments={
                "project_id": project.id,
                "status": "blocked",
                "reason": "http round-trip test",
            },
        )
        return str(approval.id), project.id


def test_pending_approvals_requires_user_role(client: TestClient) -> None:
    response = client.get("/approvals/pending", headers={"Authorization": f"Bearer {VIEWER_TOKEN}"})
    assert response.status_code == 403


def test_decide_requires_admin_role(client: TestClient) -> None:
    approval_id, _project_id = asyncio.run(_request_status_change_approval())
    response = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {USER_TOKEN}"},
    )
    assert response.status_code == 403


def test_request_then_list_then_decide_then_write_is_usable(client: TestClient) -> None:
    approval_id, project_id = asyncio.run(_request_status_change_approval())

    pending = client.get("/approvals/pending", headers={"Authorization": f"Bearer {USER_TOKEN}"})
    assert pending.status_code == 200
    assert any(a["id"] == approval_id for a in pending.json()["approvals"])

    decided = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved", "reason": "looks fine"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"

    # The approved id must now actually unlock the exact gated write it was
    # requested for — same contract `enforce_approval` gives a real MCP
    # tool call (Phase 6).
    async def _use_it() -> str:
        result = await projects_service.update_project_status(
            project_id=project_id,
            status="blocked",
            reason="http round-trip test",
            actor="tester",
            role=Role.USER,
            approval_id=approval_id,
        )
        return result.status

    status = asyncio.run(_use_it())
    assert status == "blocked"

    # And the same approval_id cannot be redeemed a second time, even for
    # the exact same arguments it was already spent on.
    async def _reuse_it() -> None:
        await projects_service.update_project_status(
            project_id=project_id,
            status="blocked",
            reason="http round-trip test",
            actor="tester",
            role=Role.USER,
            approval_id=approval_id,
        )

    try:
        asyncio.run(_reuse_it())
        raise AssertionError("expected ApprovalRequiredError on re-use")
    except ApprovalRequiredError:
        pass


def test_decide_a_nonexistent_approval_is_404(client: TestClient) -> None:
    response = client.post(
        "/approvals/00000000-0000-0000-0000-000000000000/decide",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert response.status_code == 404
