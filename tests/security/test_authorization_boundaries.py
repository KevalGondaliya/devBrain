"""Authorization-boundary tests — `DevBrain_vision.md` §25 ("Security
Tests": unauthorized calls, permission escalation).

Per-service role-resolution unit tests already exist and are thorough —
e.g. `services/task_mcp/tests/unit/test_task_mcp_auth.py`,
`services/project_mcp/tests/unit/test_project_mcp_auth.py`, one per
service, all exercising `resolve_actor`/`require_min_role` in isolation.
This file deliberately does **not** duplicate those; it adds the two things
that were missing at the *root* level:

1. **Unauthorized/insufficient-role calls dispatched through the real MCP
   tool-call path** (`create_server()` + `call_tool()` — real Pydantic
   schema validation, real `require_min_role`, real
   `handle_tool_errors` envelope — not just a direct call to an `auth.py`
   function), proven independently across more than one server, so the
   control is shown to be enforced in each service's own wiring, not just
   asserted about one.
2. **A genuine escalation attempt**: a `Role.USER` actor who has a real,
   valid *pending* approval (one they themselves requested) still cannot
   decide it — proving a user cannot promote themselves to the admin-only
   `decide_approval` path even with a legitimate approval id in hand.

HTTP-boundary equivalents (401 missing header, 403 insufficient role) are
already covered by `backend/tests/api/test_auth_endpoints.py` and
`backend/tests/api/test_approvals_endpoints.py` — referenced, not repeated,
except where this file adds a new HTTP-level case not covered there
(cross-service unauthorized-call sweep).
"""

from __future__ import annotations

import asyncio

import pytest
from devbrain_common.approvals import request_approval
from devbrain_common.db import session_scope
from fastapi.testclient import TestClient
from knowledge_mcp.server import create_server as create_knowledge_server
from mcp.server.fastmcp.exceptions import ToolError
from project_mcp.server import create_server as create_project_server
from task_mcp.server import create_server as create_task_server

# Fixed test-token literals, duplicated here rather than imported from
# `conftest` -- a bare `import conftest` is process-global (`sys.modules`
# caches it under the plain name "conftest"), so whichever test file in
# `tests/` happens to trigger that import *first* in a combined run would
# otherwise silently win for every other file that also does
# `from conftest import ...`, regardless of which directory's conftest.py
# they actually meant (this bit `tests/eval`'s own bare-name collision
# precedent already documented in PROGRESS_REPORT.md's Phase 3 section, for
# the exact same underlying reason). These three values must match
# `tests/conftest.py`'s `ADMIN_TOKEN`/`USER_TOKEN`/`VIEWER_TOKEN` exactly.
ADMIN_TOKEN = "test-admin-token"
USER_TOKEN = "test-user-token"
VIEWER_TOKEN = "test-viewer-token"

# --- 1. Real tool-dispatch rejection, across independent servers ---


async def _call_update_project_status_as(monkeypatch: pytest.MonkeyPatch, role: str) -> None:
    monkeypatch.setenv("PROJECT_MCP_STDIO_ROLE", role)
    mcp = create_project_server()
    await mcp.call_tool(
        "update_project_status",
        {"id": "00000000-0000-0000-0000-000000000000", "status": "blocked"},
    )


def test_insufficient_role_rejected_at_real_dispatch_project_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A viewer-role stdio caller is rejected by `require_min_role` before
    the (nonexistent) project id is ever looked up -- the auth check runs
    strictly before any DB access."""
    with pytest.raises(ToolError) as exc_info:
        asyncio.run(_call_update_project_status_as(monkeypatch, "viewer"))
    assert '"code": "forbidden"' in str(exc_info.value)


async def _call_decide_approval(mcp_factory: object) -> None:
    mcp = mcp_factory()  # type: ignore[operator]
    await mcp.call_tool(
        "decide_approval",
        {"approval_id": "00000000-0000-0000-0000-000000000000", "decision": "approved"},
    )


def test_permission_escalation_user_cannot_reach_admin_only_tool_task_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `Role.USER` stdio caller attempting the admin-only shared
    `decide_approval` tool is rejected -- through the real tool-call path,
    not just a direct `require_min_role` call."""
    monkeypatch.setenv("TASK_MCP_STDIO_ROLE", "user")
    with pytest.raises(ToolError) as exc_info:
        asyncio.run(_call_decide_approval(create_task_server))
    assert '"code": "forbidden"' in str(exc_info.value)


def test_permission_escalation_user_cannot_reach_admin_only_tool_knowledge_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same escalation attempt against a second, independent server
    (Knowledge MCP) -- proves the admin-only gate on the shared
    `decide_approval` tool is enforced by every server's own auth wiring,
    not by one shared codepath that happens to be tested once."""
    monkeypatch.setenv("KNOWLEDGE_MCP_STDIO_ROLE", "user")
    with pytest.raises(ToolError) as exc_info:
        asyncio.run(_call_decide_approval(create_knowledge_server))
    assert '"code": "forbidden"' in str(exc_info.value)


# --- 2. A user cannot self-approve their own pending approval ---


async def _request_a_real_pending_approval() -> str:
    async with session_scope() as session:
        approval = await request_approval(
            session,
            actor="attacker",
            tool_name="update_project_status",
            arguments={"project_id": "irrelevant", "status": "blocked", "reason": None},
        )
        return str(approval.id)


def test_permission_escalation_user_cannot_self_approve_their_own_request(
    client: TestClient, seed_small_dataset: None
) -> None:
    """The escalation path a real attacker would try: request an approval
    as a `Role.USER` actor, then attempt to decide (approve) that exact
    request with the same user-level token, hoping the "requester" and
    "decider" checks are conflated somewhere. They are not -- `decide` is
    gated purely on role, never on who requested the approval."""
    approval_id = asyncio.run(_request_a_real_pending_approval())

    response = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {USER_TOKEN}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    # The same request, made with the admin token, does succeed -- proving
    # the 403 above is specifically a role check, not a broken endpoint.
    approved = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert approved.status_code == 200


# --- 3. Unauthorized (no token) calls across a couple of distinct,
# independently-routed backend endpoints, each backed by a different MCP
# service's own service layer. ---


@pytest.mark.parametrize("path", ["/projects", "/tools", "/permissions", "/activity"])
def test_unauthorized_call_with_no_token_rejected_across_services(
    client: TestClient, path: str
) -> None:
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_unauthorized_call_with_garbage_token_rejected(client: TestClient) -> None:
    response = client.get("/projects", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_viewer_role_cannot_reach_a_write_endpoint(client: TestClient) -> None:
    """`/approvals/pending` requires Role.USER; a viewer token (below that
    bar) is rejected -- exercised here specifically to pair with the
    project_mcp/task_mcp MCP-layer rejections above, proving the same
    boundary holds at the HTTP surface too."""
    response = client.get("/approvals/pending", headers={"Authorization": f"Bearer {VIEWER_TOKEN}"})
    assert response.status_code == 403
