"""Task business logic: list/search/get/create/update/complete, per
`DevBrain_vision.md` §11.3.

Security note (ORCHESTRATION.md): `title`/`description`/`blocked_reason` are
always treated as opaque text data — never `eval`/`exec`d or passed to a
shell, only ever persisted or ILIKE-matched.

Idempotency (DevBrain_vision.md §16): `create_task` accepts an optional
`idempotency_key`. A retried call with the same key returns the
already-created task instead of inserting a duplicate — via the shared
`devbrain_common.idempotency.check_idempotent_replay` (Phase 6; this
service's own `repositories/idempotency_repository.py` copy of the same
audit_logs-JSONB lookup was deleted once this generalized, per
PROGRESS_REPORT.md Phase 4/6).

Human-in-the-loop approval (DevBrain_vision.md §9/§10, Phase 6):
`create_task`/`update_task`/`complete_task` are medium-risk writes (see
`risk.py`) gated by `devbrain_common.approvals.enforce_approval` —
`Role.ADMIN` callers bypass (flagged `approval_bypassed_by_admin=true` in
the audit row), `Role.USER` callers must supply a valid `approval_id`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from devbrain_common import idempotency as idempotency  # explicit re-export: tests monkeypatch this
from devbrain_common.approvals import enforce_approval
from devbrain_common.audit import record_audit_event
from devbrain_common.auth import Role
from devbrain_common.errors import NotFoundError, ValidationError
from devbrain_common.models import Task

from task_mcp.repositories import projects_repository as projects_repository
from task_mcp.repositories import tasks_repository as tasks_repository
from task_mcp.repositories import unit_of_work as uow

TASK_STATUSES = ("todo", "in_progress", "blocked", "done", "cancelled")


@dataclass(frozen=True)
class TaskDTO:
    id: str
    project_id: str
    title: str
    description: str | None
    status: str
    priority: str | None
    assignee: str | None
    due_date: datetime | None
    blocked_reason: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def task_to_dto(task: Task) -> TaskDTO:
    return TaskDTO(
        id=str(task.id),
        project_id=str(task.project_id),
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        assignee=task.assignee,
        due_date=task.due_date,
        blocked_reason=task.blocked_reason,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError(f"{field_name!r} is not a valid UUID: {value!r}") from exc


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"{field_name!r} is not a valid ISO 8601 datetime: {value!r}"
        raise ValidationError(msg) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


async def list_tasks(*, project_id: str | None = None, status: str | None = None) -> list[TaskDTO]:
    if status is not None and status not in TASK_STATUSES:
        raise ValidationError(f"status must be one of {TASK_STATUSES}.")
    parsed_project_id = _parse_uuid(project_id, "project_id") if project_id else None
    async with uow.unit_of_work() as session:
        tasks = await tasks_repository.list_by_filters(
            session, project_id=parsed_project_id, status=status
        )
        return [task_to_dto(t) for t in tasks]


async def search_tasks(*, query: str, limit: int = 20) -> list[TaskDTO]:
    if not query.strip():
        raise ValidationError("query must not be empty.")
    async with uow.unit_of_work() as session:
        tasks = await tasks_repository.search(session, query, limit)
        return [task_to_dto(t) for t in tasks]


async def get_task(*, task_id: str) -> TaskDTO:
    async with uow.unit_of_work() as session:
        task = await tasks_repository.get_by_id(session, _parse_uuid(task_id, "id"))
        if task is None:
            raise NotFoundError("Task not found.")
        return task_to_dto(task)


async def create_task(
    *,
    project_id: str,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    due_date: str | None = None,
    idempotency_key: str | None = None,
    actor: str,
    role: Role,
    approval_id: str | None = None,
) -> TaskDTO:
    if not title.strip():
        raise ValidationError("title must not be empty.")

    call_arguments = {
        "project_id": project_id,
        "title": title,
        "description": description,
        "priority": priority,
        "assignee": assignee,
        "due_date": due_date,
    }

    started = time.monotonic()
    async with uow.unit_of_work() as session:
        replay = await idempotency.check_idempotent_replay(
            session,
            actor=actor,
            tool_name="create_task",
            idempotency_key=idempotency_key,
            result_key="result_task_id",
            get_existing=lambda s, id_str: tasks_repository.get_by_id(s, uuid.UUID(id_str)),
            started=started,
        )
        if replay is not None:
            return task_to_dto(replay)

        # Phase 6 human-in-the-loop gate (devbrain_common.approvals):
        # Role.ADMIN bypasses (flagged in the audit row below); Role.USER
        # must supply a valid, matching, unconsumed approval_id or this
        # raises ApprovalRequiredError before anything is mutated.
        bypassed_as_admin = await enforce_approval(
            session,
            role=role,
            actor=actor,
            tool_name="create_task",
            arguments=call_arguments,
            approval_id=approval_id,
        )

        project_uuid = _parse_uuid(project_id, "project_id")
        if not await projects_repository.exists(session, project_uuid):
            raise NotFoundError(f"Project {project_id!r} not found.")

        task = Task(
            id=uuid.uuid4(),
            project_id=project_uuid,
            title=title.strip(),
            description=description,
            status="todo",
            priority=priority,
            assignee=assignee,
            due_date=_parse_datetime(due_date, "due_date") if due_date else None,
        )
        tasks_repository.insert(session, task)
        await session.flush()

        await record_audit_event(
            session,
            actor=actor,
            tool_name="create_task",
            arguments={
                "project_id": project_id,
                "title": title,
                "idempotency_key": idempotency_key,
                "result_task_id": str(task.id),
                "approval_id": approval_id,
                "approval_bypassed_by_admin": bypassed_as_admin,
            },
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        persisted = await tasks_repository.get_by_id(session, task.id)
        assert persisted is not None  # noqa: S101 - just inserted, in the same transaction
        return task_to_dto(persisted)


async def _apply_update(
    *,
    tool_name: str,
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    due_date: str | None = None,
    blocked_reason: str | None = None,
    actor: str,
    role: Role,
    approval_id: str | None = None,
    approval_arguments: dict[str, object] | None = None,
) -> TaskDTO:
    """`approval_arguments` is the exact dict a caller must have passed to
    `request_approval` for `tool_name` — defaults to every field this
    function accepts (matching `update_task`'s own public signature).
    `complete_task` passes a narrower `{"task_id": ...}` dict instead, since
    that's its actual public signature (see `complete_task` below)."""
    if status is not None and status not in TASK_STATUSES:
        raise ValidationError(f"status must be one of {TASK_STATUSES}.")

    if approval_arguments is None:
        approval_arguments = {
            "task_id": task_id,
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "assignee": assignee,
            "due_date": due_date,
            "blocked_reason": blocked_reason,
        }

    started = time.monotonic()
    async with uow.unit_of_work() as session:
        # Phase 6 human-in-the-loop gate — see create_task's comment above
        # for the admin-bypass / user-needs-approval_id shape.
        bypassed_as_admin = await enforce_approval(
            session,
            role=role,
            actor=actor,
            tool_name=tool_name,
            arguments=approval_arguments,
            approval_id=approval_id,
        )

        task = await tasks_repository.get_by_id(session, _parse_uuid(task_id, "id"))
        if task is None:
            raise NotFoundError("Task not found.")

        if title is not None and title.strip():
            task.title = title.strip()
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority
        if assignee is not None:
            task.assignee = assignee
        if due_date is not None:
            task.due_date = _parse_datetime(due_date, "due_date")
        if blocked_reason is not None:
            task.blocked_reason = blocked_reason
        if status is not None:
            task.status = status

        # Invariant (mirrors scripts/generators/tasks.py's seed data
        # convention, enforced here for writes too): `blocked_reason` is set
        # iff `status == "blocked"`.
        if task.status == "blocked" and not task.blocked_reason:
            raise ValidationError("blocked_reason is required when status is 'blocked'.")
        if task.status != "blocked" and task.blocked_reason is not None:
            task.blocked_reason = None

        await session.flush()

        await record_audit_event(
            session,
            actor=actor,
            tool_name=tool_name,
            arguments={
                "task_id": task_id,
                "title_changed": title is not None,
                "status": status,
                "priority_changed": priority is not None,
                "assignee_changed": assignee is not None,
                "due_date_changed": due_date is not None,
                "blocked_reason_changed": blocked_reason is not None,
                "approval_id": approval_id,
                "approval_bypassed_by_admin": bypassed_as_admin,
            },
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        persisted = await tasks_repository.get_by_id(session, task.id)
        assert persisted is not None  # noqa: S101 - just updated, in the same transaction
        return task_to_dto(persisted)


async def update_task(
    *,
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    due_date: str | None = None,
    blocked_reason: str | None = None,
    actor: str,
    role: Role,
    approval_id: str | None = None,
) -> TaskDTO:
    return await _apply_update(
        tool_name="update_task",
        task_id=task_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        assignee=assignee,
        due_date=due_date,
        blocked_reason=blocked_reason,
        actor=actor,
        role=role,
        approval_id=approval_id,
    )


async def complete_task(
    *, task_id: str, actor: str, role: Role, approval_id: str | None = None
) -> TaskDTO:
    """Mark a task `done` — a thin, separately-audited (`tool_name=
    "complete_task"`) wrapper around the same update path `update_task`
    uses, per `DevBrain_vision.md` §11.3 listing it as its own tool.
    Approval matching uses `complete_task`'s own (narrower) public
    signature — just `task_id` — not `update_task`'s full field list."""
    return await _apply_update(
        tool_name="complete_task",
        task_id=task_id,
        status="done",
        actor=actor,
        role=role,
        approval_id=approval_id,
        approval_arguments={"task_id": task_id},
    )
