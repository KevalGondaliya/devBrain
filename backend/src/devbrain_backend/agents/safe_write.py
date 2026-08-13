"""Safe AI Action — DevBrain_vision.md §9 ("Example Write Workflow") / §30
(Flagship Demo #4 "Safe AI Action"): an agent that *proposes* a write and
participates in Phase 6's human approval gate rather than ever calling a
write service function directly with elevated privilege.

Two-step flow, mirroring exactly what a real MCP client retrying after
approval would do (and exactly Phase 6's own contract — see
`devbrain_common.approvals`' module docstring):

  1. `propose_create_task()` — builds the exact `arguments` dict
     `task_mcp.services.tasks_service.create_task` will match against (its
     own `call_arguments`), and calls
     `devbrain_common.approvals.request_approval` — never `create_task`
     itself. Returns the `approval_id` plus a human-readable summary of
     what is being proposed, for a human (`Role.ADMIN`, via
     `devbrain_common.approvals.decide_approval`) to review and approve or
     reject.
  2. `execute_approved_task_creation()` — the "approved retry": calls
     `tasks_service.create_task` with `role=Role.USER` (deliberately never
     `Role.ADMIN` — this orchestrator is never granted admin, so it cannot
     bypass the approval gate even if it wanted to) and the `approval_id`
     from step 1. If no valid, matching, unconsumed approval exists,
     `create_task`'s own `enforce_approval` call raises
     `ApprovalRequiredError` before anything is mutated — exactly as it
     would for a direct MCP tool call with a missing/stale `approval_id`.

Nothing in this module ever mutates a task on its own authority: step 2
only succeeds because `enforce_approval` independently re-validates the
approval against the exact same `tool_name`/`arguments`, redeemed once.
This is the property `tests/security/test_prompt_injection_defense.py`
exercises: even a "compliant-sounding" LLM response can never turn into a
task write without going through this same two-step, human-gated path.
"""

from __future__ import annotations

from dataclasses import dataclass

from devbrain_common.approvals import request_approval
from devbrain_common.auth import Role
from devbrain_common.db import session_scope
from task_mcp.services.tasks_service import TaskDTO, create_task


@dataclass(frozen=True)
class ProposedTaskAction:
    approval_id: str
    summary: str
    call_arguments: dict[str, object]


async def propose_create_task(
    *,
    actor: str,
    project_id: str,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    due_date: str | None = None,
) -> ProposedTaskAction:
    """Prepare (never execute) a `create_task` write.

    Returns an `approval_id` that a human must approve via
    `devbrain_common.approvals.decide_approval` (`Role.ADMIN`-only, enforced
    by whichever MCP server's `decide_approval` tool is used to grant it —
    see `devbrain_common.approval_tools`) before
    `execute_approved_task_creation` below can succeed.
    """
    # Must match `tasks_service.create_task`'s own internal `call_arguments`
    # dict exactly (field-for-field) — `consume_approval` compares with `==`.
    call_arguments: dict[str, object] = {
        "project_id": project_id,
        "title": title,
        "description": description,
        "priority": priority,
        "assignee": assignee,
        "due_date": due_date,
    }
    async with session_scope() as session:
        approval = await request_approval(
            session,
            actor=actor,
            tool_name="create_task",
            arguments=call_arguments,
            risk_tier="medium",
        )
        approval_id = str(approval.id)

    due_clause = f" (due {due_date})" if due_date else ""
    summary = (
        f"Propose creating a {priority or 'normal'}-priority task {title!r} "
        f"in project {project_id}{due_clause}. Awaiting approval "
        f"(approval_id={approval_id})."
    )
    return ProposedTaskAction(
        approval_id=approval_id, summary=summary, call_arguments=call_arguments
    )


async def execute_approved_task_creation(
    *,
    actor: str,
    approval_id: str,
    project_id: str,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    due_date: str | None = None,
) -> TaskDTO:
    """The "approved retry": redeems `approval_id` through `create_task`'s
    own `enforce_approval` gate. `role=Role.USER` always — this orchestrator
    is never granted the elevated admin role. The keyword arguments here must match
    `propose_create_task`'s `call_arguments` exactly, or `enforce_approval`
    raises `ApprovalRequiredError` (from `consume_approval`'s exact-dict
    match) and nothing is mutated.
    """
    return await create_task(
        project_id=project_id,
        title=title,
        description=description,
        priority=priority,
        assignee=assignee,
        due_date=due_date,
        actor=actor,
        role=Role.USER,
        approval_id=approval_id,
    )
