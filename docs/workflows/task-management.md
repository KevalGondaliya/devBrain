# Workflow: Task Management (Safe AI Action)

`DevBrain_vision.md` §9/§30 (Flagship Demo #4, "Safe AI Action"). This is
the one workflow that writes data, and the one built specifically to prove
DevBrain never lets an LLM author a write on its own authority. Orchestrator:
`backend/src/devbrain_backend/agents/safe_write.py`.

## The two-step flow

1. **`propose_create_task(...)`** — builds the exact `arguments` dict
   `task_mcp.services.tasks_service.create_task` will later match against,
   and calls `devbrain_common.approvals.request_approval`. It never calls
   `create_task` itself. Returns an `approval_id` and a human-readable
   summary for a `Role.ADMIN` to review.
2. **(human) `decide_approval`** — via any server's `decide_approval` MCP
   tool, or `POST /approvals/{id}/decide` over HTTP.
3. **`execute_approved_task_creation(...)`** — the approved retry: calls
   `tasks_service.create_task` with `role=Role.USER` (hardcoded — this
   orchestrator is never granted `Role.ADMIN`) and the `approval_id`. If no
   valid, matching, unconsumed approval exists, `enforce_approval` raises
   `ApprovalRequiredError` before anything mutates.

## Sample request/response

`/chat` recognizes the intent but explicitly refuses to execute it from free
text (see `docs/mcp/security.md`'s prompt-injection section for why):

```bash
curl -s http://localhost:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a high-priority task to finish the OAuth documentation tomorrow", "history": []}'
```

```json
{
  "reply": "I can't create a task directly from chat text — DevBrain never lets freeform input author a write tool's arguments...",
  "intent": "safe_write",
  "orchestrator": null,
  "data": {}
}
```

The real flow (typed fields, in-process — what `DEMO.md` step 5 and
`tests/eval/scenarios.json`'s `create_task_requires_approval` scenario
exercise) is:

```python
proposal = await safe_write.propose_create_task(
    actor="user:demo",
    project_id=project_id,
    title="Finish OAuth documentation",
    priority="high",
    due_date="2026-08-14T00:00:00+00:00",
)
# -> ProposedTaskAction(approval_id=..., summary="Propose creating a high-priority task ...")

await decide_approval(
    session, approval_id=proposal.approval_id, decision="approved", decided_by="human-admin"
)

task = await safe_write.execute_approved_task_creation(
    actor="user:demo",
    approval_id=proposal.approval_id,
    project_id=project_id,
    title="Finish OAuth documentation",
    priority="high",
    due_date="2026-08-14T00:00:00+00:00",
)
# -> TaskDTO(title="Finish OAuth documentation", priority="high", ...)
```

Skipping step 2 (or approving a *different* set of arguments than step 3
supplies) makes step 3 raise `ApprovalRequiredError` — proven directly in
`backend/tests/integration/test_safe_write_integration.py`.

## Where this is tested

`backend/tests/integration/test_safe_write_integration.py`,
`backend/tests/api/test_approvals_endpoints.py` (the HTTP round trip),
`tests/eval/scenarios.json` (`create_task_requires_approval`,
`delete_completed_tasks_requires_admin_approval`), `tests/e2e/test_full_stack_e2e.py`
(propose → approve → execute → audit log, over real HTTP against a real
DB), `DEMO.md` step 5.
