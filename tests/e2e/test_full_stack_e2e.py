"""True end-to-end tests — `DevBrain_vision.md` §25 ("E2E Tests":
User -> Claude -> MCP -> Database -> Approval -> Write -> Audit -> Final
response).

Every request below goes through the real FastAPI backend
(`fastapi.testclient.TestClient` against the real `app`, HTTP request/
response, real bearer-token auth) into real service functions, against a
real, seeded `db_test` — nothing here is mocked or monkeypatched. This is
the one place in the test suite that proves the *whole* stack wired
together, not one layer at a time (that's what `tests/unit`/
`tests/integration` are for) and not a fixed hand-mapped question-to-call
proxy (that's `tests/eval`).

Individual pieces of this flow already have focused HTTP-layer coverage
(`backend/tests/api/test_approvals_endpoints.py`,
`backend/tests/api/test_read_endpoints.py`,
`backend/tests/api/test_chat_endpoint.py`) — this file's job is chaining
them into one continuous request path per `DevBrain_vision.md`'s own E2E
diagram, ending each test at a *different* read endpoint than the one that
made the write, so the assertion genuinely exercises "the write really
landed and is independently observable," not just "the endpoint that made
the write says it worked."
"""

from __future__ import annotations

import asyncio

from devbrain_common.approvals import request_approval
from devbrain_common.auth import Role
from devbrain_common.db import session_scope
from devbrain_common.errors import ApprovalRequiredError
from fastapi.testclient import TestClient
from knowledge_mcp.services import notes_service
from project_mcp.services import projects_service

# Fixed test-token literals, duplicated here rather than imported from
# `conftest` -- a bare `import conftest` is process-global (`sys.modules`
# caches it under the plain name "conftest"), so whichever test file in
# `tests/` happens to trigger that import *first* in a combined run would
# otherwise silently win for every other file that also does
# `from conftest import ...`, regardless of which directory's conftest.py
# they actually meant. These three values must match `tests/conftest.py`'s
# `ADMIN_TOKEN`/`USER_TOKEN`/`VIEWER_TOKEN` exactly.
ADMIN_TOKEN = "test-admin-token"
USER_TOKEN = "test-user-token"
VIEWER_TOKEN = "test-viewer-token"


async def _request_status_change_approval() -> tuple[str, str, str]:
    projects = await projects_service.list_projects()
    project = projects[0]
    previous_status = project.status
    async with session_scope() as session:
        approval = await request_approval(
            session,
            actor="e2e-test-user",
            tool_name="update_project_status",
            arguments={
                "project_id": project.id,
                "status": "blocked",
                "reason": "e2e full-stack test",
            },
        )
        return str(approval.id), project.id, previous_status


def test_write_approval_flow_end_to_end_through_http(client: TestClient) -> None:
    """User -> MCP (proposal) -> Database (pending approval) -> Approval
    (admin decides over HTTP) -> Write (executes for real) -> Audit (shows
    up in GET /activity) -> Final response (GET /projects reflects the new
    state) -- every step of `DevBrain_vision.md`'s E2E diagram, once each,
    in order.
    """
    # 1. A real login round trip resolves each token's role over HTTP —
    # the actual credential path a frontend/Claude client would use.
    user_login = client.post("/auth/login", json={"token": USER_TOKEN})
    assert user_login.status_code == 200
    assert user_login.json()["role"] == "user"

    # 2. Propose the write (mirrors what a real orchestrator, e.g.
    # devbrain_backend.agents.safe_write, does in-process before a human
    # ever sees it — there is deliberately no HTTP endpoint for this step,
    # see approvals_router.py's own module docstring).
    approval_id, project_id, previous_status = asyncio.run(_request_status_change_approval())

    # 3. The proposal is now visible to any Role.USER caller over HTTP.
    pending = client.get("/approvals/pending", headers={"Authorization": f"Bearer {USER_TOKEN}"})
    assert pending.status_code == 200
    assert any(a["id"] == approval_id for a in pending.json()["approvals"])

    # 4. A non-admin cannot decide it (the same escalation boundary
    # `tests/security/test_authorization_boundaries.py` checks in
    # isolation — included here as one step of the continuous flow, not
    # duplicated logic).
    denied = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {USER_TOKEN}"},
    )
    assert denied.status_code == 403

    # 5. An admin approves it, over HTTP.
    decided = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved", "reason": "looks safe"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"

    # 6. The write itself executes through the real service, redeeming the
    # now-approved approval_id (exactly what a retried MCP tool call would
    # do — there is no "execute" HTTP endpoint either, by the same design
    # documented in approvals_router.py).
    async def _execute() -> str:
        result = await projects_service.update_project_status(
            project_id=project_id,
            status="blocked",
            reason="e2e full-stack test",
            actor="e2e-test-user",
            role=Role.USER,
            approval_id=approval_id,
        )
        return result.status

    new_status = asyncio.run(_execute())
    assert new_status == "blocked"
    assert new_status != previous_status

    # 7. Audit: the write is now visible over HTTP, newest-first, with the
    # right server/tool/status attribution.
    activity = client.get("/activity?limit=5", headers={"Authorization": f"Bearer {USER_TOKEN}"})
    assert activity.status_code == 200
    items = activity.json()["items"]
    matching = [i for i in items if i["tool"] == "update_project_status"]
    assert matching, "the write must be visible in the audit trail"
    assert matching[0]["server"] == "project-mcp"
    assert matching[0]["status"] == "SUCCESS"
    assert matching[0]["arguments"]["project_id"] == project_id

    # 8. Final response: the new state is independently observable through
    # a completely different read endpoint than the one that made the
    # write or read the audit trail -- proving this is a real, durable
    # database change, not an artifact of the write endpoint's own response.
    projects_after = client.get("/projects", headers={"Authorization": f"Bearer {VIEWER_TOKEN}"})
    assert projects_after.status_code == 200
    updated = next(p for p in projects_after.json()["projects"] if p["id"] == project_id)
    assert updated["status"] == "blocked"

    # And the same approval_id cannot be redeemed a second time.
    async def _reuse() -> bool:
        try:
            await projects_service.update_project_status(
                project_id=project_id,
                status="active",
                reason="replay attempt",
                actor="e2e-test-user",
                role=Role.USER,
                approval_id=approval_id,
            )
            return False
        except ApprovalRequiredError:
            return True

    assert asyncio.run(_reuse()), "a consumed approval must not be redeemable twice"


def test_chat_driven_write_reflected_in_audit_log_and_underlying_data(client: TestClient) -> None:
    """A second, independent full-stack path: `POST /chat`'s weekly_digest
    intent (Claude-facing surface) actually creates a note through the real
    Knowledge MCP service layer, and that write is independently visible
    both in the audit trail (`GET /activity`) and by directly reading the
    note back out of the database through Knowledge MCP's own service --
    proving the chat response's claim ("created note X") is not just an
    echo of its own input.
    """
    response = client.post(
        "/chat",
        json={"message": "weekly digest please", "history": []},
        headers={"Authorization": f"Bearer {USER_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "weekly_digest"
    digest_title = body["data"]["digest_note"]["title"]

    activity = client.get("/activity?limit=5", headers={"Authorization": f"Bearer {USER_TOKEN}"})
    assert activity.status_code == 200
    matching = [i for i in activity.json()["items"] if i["tool"] == "notes.create"]
    assert matching, "the chat-driven note creation must be visible in the audit trail"
    assert matching[0]["status"] == "SUCCESS"
    # Weekly digest runs as a system process (role=Role.ADMIN, a documented
    # bypass case, see backend/src/devbrain_backend/agents/weekly_digest.py)
    # -- the bypass itself must be visible in the audit row, never silent.
    assert matching[0]["arguments"].get("approval_bypassed_by_admin") is True

    async def _read_it_back() -> str:
        note = await notes_service.get_note(slug=notes_service.slugify(digest_title))
        return note.title

    assert asyncio.run(_read_it_back()) == digest_title
