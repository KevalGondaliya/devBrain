# Data flow — one request, every layer it passes through

Two concrete traces: a read (no approval gate) and a medium-risk write (full
approval gate). Both are real, current code paths — line up each step
against the file it names.

## Read: `get_task(id=...)`

```
1. MCP client (Claude, or an HTTP caller via the backend) invokes get_task
   with {"id": "<uuid>"}.
        |
        v
2. FastMCP validates the input against the function's type hints (str) —
   a non-string / missing id is rejected before the function body runs.
        |
        v
3. services/task_mcp/src/task_mcp/tools/tasks_tools.py::get_task
        require_min_role(ctx, Role.VIEWER)
        -> devbrain_common.mcp_auth.make_require_min_role's closure:
           resolve actor + Role from the MCP Context (bearer token over
           HTTP, fixed TASK_MCP_STDIO_ROLE over stdio), then
           devbrain_common.ratelimit.get_rate_limiter().check(actor)
           (429 RateLimitedError if exceeded), then
           devbrain_common.auth.check_role(role, Role.VIEWER)
           (403 ForbiddenError if insufficient).
        |
        v
4. tasks_service.get_task(task_id=id)
   — services/task_mcp/src/task_mcp/services/tasks_service.py
   opens one unit_of_work() (= devbrain_common.db.session_scope()) and
   calls the repository.
        |
        v
5. tasks_repository.get_by_id(session, task_id)
   — parameterized SQLAlchemy SELECT, no raw SQL, populate_existing=True
   so a read reflects the freshest in-transaction state.
        |
        v
6. PostgreSQL returns the row (or none -> NotFoundError, 404).
        |
        v
7. Service maps the ORM row to a TaskDTO; tool wraps it via dto_to_dict()
   and returns it — or, on any DevBrainError, handle_tool_errors
   (packages/common/src/devbrain_common/mcp_tooling.py) catches it and
   returns {"error": {"code", "message"}} instead of a raw traceback.
```

No audit row is written — reads are not audited (`ORCHESTRATION.md` only
requires auditing writes; every server's `risk.py` marks reads `LOW`).

## Write: `create_task(...)` as `Role.USER` (medium risk, approval required)

```
1. Caller (a Role.USER token) calls create_task with project_id/title/...
   and, if it already has one, an approval_id.
        |
        v
2. Pydantic/type-hint validation (task_mcp/tools/tasks_tools.py::create_task)
   — title length-bounded via Field(min_length=1, max_length=300), etc.
        |
        v
3. require_min_role(ctx, Role.USER) — same auth+rate-limit check as the
   read path, higher bar. A Role.VIEWER caller is rejected here (403),
   never reaching step 4.
        |
        v
4. tasks_service.create_task(..., role=Role.USER, approval_id=...)
   a. Idempotency check first (devbrain_common.idempotency
      .check_idempotent_replay): if idempotency_key matches a prior
      successful create_task call (looked up in audit_logs.arguments),
      return that task directly — skip straight to step 8, no new write,
      no approval re-check.
   b. Otherwise, build call_arguments = {project_id, title, description,
      priority, assignee, due_date} — the exact dict an approval must
      match.
        |
        v
5. devbrain_common.approvals.enforce_approval(session, role=Role.USER,
   actor=..., tool_name="create_task", arguments=call_arguments,
   approval_id=approval_id)
     - No approval_id -> ApprovalRequiredError (403, code
       "approval_required") RIGHT HERE. Nothing is mutated. The caller
       must first call request_approval with the identical arguments
       dict, wait for a Role.ADMIN to call decide_approval(approved), then
       retry this exact call with the resulting approval_id.
     - Valid approval_id -> consume_approval(): loads the Approval row,
       checks tool_name+arguments match by ==, status=="approved", and
       consumed_at is still None. Any mismatch -> ApprovalRequiredError.
       On success, stamps consumed_at (single-use) and returns.
        |
        v
6. tasks_repository.create(session, ...) — parameterized INSERT.
        |
        v
7. devbrain_common.audit.record_audit_event(session, actor=..., 
   tool_name="create_task", arguments=redact_arguments(call_arguments),
   status="success", duration_ms=...) — same transaction as step 6, via
   the same unit_of_work(). If step 5 or 6 raised instead, the caller
   (tool wrapper's handle_tool_errors, or the service's own except block)
   still records status="denied"/"error" — a rejected/failed call is
   audited too, not silently dropped.
        |
        v
8. session_scope()'s commit (with devbrain_common.retry.retry_async around
   just the commit call, for transient connection errors) — task row and
   audit row land atomically.
        |
        v
9. TaskDTO returned up through the service -> tool -> handle_tool_errors ->
   MCP response, stamped with risk_tier="medium",
   approval_recommended=True.
```

A `Role.ADMIN` caller takes the same path through step 5, except
`enforce_approval` returns `True` immediately (no DB access on that branch)
— the service must then pass `approval_bypassed_by_admin=true` into the
audit row's context, so the bypass is visible in `GET /activity` /
`audit_logs`, never silent.

## High-risk write: `notes.delete` (admin role AND approval, not either/or)

Same shape as above through role/rate-limit check, except the gate itself
(`knowledge_mcp.services.notes_service._enforce_high_risk_approval`, **not**
`devbrain_common.approvals.enforce_approval`) requires both conditions
together:

```
require_min_role(ctx, Role.ADMIN)   <- transport-level gate, non-admin
                                         rejected before the service is
                                         even reached
        |
        v
role.at_least(Role.ADMIN)?  -- no --> ForbiddenError (no DB access)
        | yes
        v
approval_id valid, matching, unconsumed?  -- no --> ApprovalRequiredError
        | yes
        v
consume_approval() spends it; soft-delete executes; audit row written
```

`Role.ADMIN` alone is not sufficient and a valid approval alone (without
admin) is not sufficient — both are required simultaneously. See
`services/knowledge_mcp/tests/integration/test_approval_gate_integration.py`
for the test proving all four role×approval combinations resolve correctly.

## Where this is exercised in tests

- `services/task_mcp/tests/integration/*` — the full read/write traces above
  against a real `db_test`.
- `services/knowledge_mcp/tests/integration/test_approval_gate_integration.py`
  — the high-risk `notes.delete` variant.
- `tests/e2e/test_full_stack_e2e.py` (this phase) — the identical write trace
  driven through the FastAPI HTTP surface end to end: `TestClient` request →
  `require_role` FastAPI dependency → agent/service call → real `db_test`
  write → `POST /approvals/{id}/decide` → retry → `GET /activity` shows the
  resulting audit row.
