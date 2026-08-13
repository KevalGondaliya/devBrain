"""Happy-path coverage for the read-only endpoints: /tools, /permissions,
/projects, /activity."""

from __future__ import annotations

import asyncio

from devbrain_common.auth import Role
from fastapi.testclient import TestClient
from project_mcp.services import projects_service

from conftest import USER_TOKEN, VIEWER_TOKEN

_EXPECTED_SERVERS = {"knowledge-mcp", "project-mcp", "task-mcp", "github-mcp", "calendar-mcp"}


def test_tools_lists_all_five_servers_with_real_tool_names(client: TestClient) -> None:
    response = client.get("/tools", headers={"Authorization": f"Bearer {VIEWER_TOKEN}"})
    assert response.status_code == 200
    servers = {entry["server"]: entry["tools"] for entry in response.json()["servers"]}
    assert set(servers) == _EXPECTED_SERVERS
    assert "create_task" in servers["task-mcp"]
    assert "notes.create" in servers["knowledge-mcp"]
    # The shared approval tools are mounted on every server.
    for tools in servers.values():
        assert {"request_approval", "list_pending_approvals", "decide_approval"} <= set(tools)


def test_permissions_matrix_reflects_real_risk_tiers_and_roles(client: TestClient) -> None:
    response = client.get("/permissions", headers={"Authorization": f"Bearer {VIEWER_TOKEN}"})
    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["viewer", "user", "admin"]

    task_tools = {t["tool"]: t for t in body["servers"]["task-mcp"]["tools"]}
    assert task_tools["list_tasks"]["risk_tier"] == "low"
    assert task_tools["list_tasks"]["min_role"] == "viewer"
    assert task_tools["create_task"]["risk_tier"] == "medium"
    assert task_tools["create_task"]["min_role"] == "user"
    assert task_tools["create_task"]["approval_required"] is True

    # Knowledge MCP has its own risk.py (added by the Phase 6 gap-fix
    # addendum) and is now introspected uniformly with the other four
    # services: risk_tier -> min_role (low/medium/high -> viewer/user/admin).
    knowledge_tools = {t["tool"]: t for t in body["servers"]["knowledge-mcp"]["tools"]}
    assert knowledge_tools["notes.get"]["risk_tier"] == "low"
    assert knowledge_tools["notes.get"]["min_role"] == "viewer"
    assert knowledge_tools["notes.create"]["risk_tier"] == "medium"
    assert knowledge_tools["notes.create"]["min_role"] == "user"
    assert knowledge_tools["notes.create"]["approval_required"] is True
    # notes.delete is Knowledge MCP's one high-risk tool (admin AND
    # approval both required, per the gap-fix's design) — /permissions must
    # report its stricter min_role as "admin", not the medium-risk "user".
    assert knowledge_tools["notes.delete"]["risk_tier"] == "high"
    assert knowledge_tools["notes.delete"]["min_role"] == "admin"
    assert knowledge_tools["notes.delete"]["approval_required"] is True


def test_projects_lists_seeded_projects(client: TestClient) -> None:
    response = client.get("/projects", headers={"Authorization": f"Bearer {VIEWER_TOKEN}"})
    assert response.status_code == 200
    projects = response.json()["projects"]
    assert len(projects) == 2  # --size small seeds exactly 2 projects
    assert all(p["name"] for p in projects)


def test_activity_lists_recent_audit_rows_newest_first(client: TestClient) -> None:
    async def _make_two_writes() -> str:
        projects = await projects_service.list_projects()
        project_id = projects[0].id
        await projects_service.update_project_status(
            project_id=project_id, status="blocked", reason="first", actor="seed", role=Role.ADMIN
        )
        await projects_service.update_project_status(
            project_id=project_id, status="active", reason="second", actor="seed", role=Role.ADMIN
        )
        return project_id

    asyncio.run(_make_two_writes())

    response = client.get("/activity?limit=2", headers={"Authorization": f"Bearer {USER_TOKEN}"})
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert len(body["items"]) == 2
    assert body["total"] >= 2
    # Newest first: the "second" update's row comes before "first"'s.
    assert body["items"][0]["arguments"]["reason"] == "second"
    assert body["items"][0]["server"] == "project-mcp"
    assert body["items"][0]["tool"] == "update_project_status"
    assert body["items"][0]["status"] == "SUCCESS"
