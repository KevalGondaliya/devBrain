"""`tasks_service` orchestration — repository layer mocked."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from _task_mcp_fakes import fake_unit_of_work
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, NotFoundError, ValidationError
from task_mcp.repositories import unit_of_work as uow
from task_mcp.services import tasks_service


@dataclass
class FakeTask:
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None = None
    status: str = "todo"
    priority: str | None = None
    assignee: str | None = None
    due_date: datetime | None = None
    blocked_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class FakeAuditLog:
    tool_name: str
    arguments: dict[str, object]
    status: str = "success"


@pytest.fixture(autouse=True)
def _patch_unit_of_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uow, "unit_of_work", fake_unit_of_work)


@pytest.fixture(autouse=True)
def _no_real_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_record_audit_event(session: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(tasks_service, "record_audit_event", fake_record_audit_event)


# --- list_tasks / search_tasks / get_task -----------------------------------


async def test_list_tasks_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        await tasks_service.list_tasks(status="nonsense")


async def test_list_tasks_returns_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    project_id = uuid.uuid4()
    tasks = [FakeTask(id=uuid.uuid4(), project_id=project_id, title="A")]

    async def fake_list_by_filters(
        session: object, *, project_id: uuid.UUID | None, status: str | None, limit: int = 200
    ) -> list[FakeTask]:
        return tasks

    monkeypatch.setattr(tasks_service.tasks_repository, "list_by_filters", fake_list_by_filters)

    result = await tasks_service.list_tasks(project_id=str(project_id))
    assert result[0].title == "A"


async def test_search_tasks_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        await tasks_service.search_tasks(query="   ")


async def test_search_tasks_returns_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    matched = [FakeTask(id=uuid.uuid4(), project_id=uuid.uuid4(), title="OAuth docs")]

    async def fake_search(session: object, query: str, limit: int) -> list[FakeTask]:
        assert query == "oauth"
        return matched

    monkeypatch.setattr(tasks_service.tasks_repository, "search", fake_search)

    result = await tasks_service.search_tasks(query="oauth")
    assert result[0].title == "OAuth docs"


async def test_get_task_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await tasks_service.get_task(task_id=str(uuid.uuid4()))


async def test_get_task_invalid_uuid_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        await tasks_service.get_task(task_id="not-a-uuid")


# --- create_task --------------------------------------------------------


async def test_create_task_rejects_empty_title() -> None:
    with pytest.raises(ValidationError):
        await tasks_service.create_task(
            project_id=str(uuid.uuid4()), title="   ", actor="tester", role=Role.ADMIN
        )


async def test_create_task_project_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_exists(session: object, project_id: uuid.UUID) -> bool:
        return False

    monkeypatch.setattr(tasks_service.projects_repository, "exists", fake_exists)

    with pytest.raises(NotFoundError):
        await tasks_service.create_task(
            project_id=str(uuid.uuid4()), title="Do the thing", actor="tester", role=Role.ADMIN
        )


async def test_create_task_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    project_id = uuid.uuid4()
    created: dict[str, FakeTask] = {}

    async def fake_exists(session: object, pid: uuid.UUID) -> bool:
        return True

    def fake_insert(session: object, task: object) -> None:
        created["task"] = task  # type: ignore[assignment]

    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> FakeTask:
        return created["task"]

    monkeypatch.setattr(tasks_service.projects_repository, "exists", fake_exists)
    monkeypatch.setattr(tasks_service.tasks_repository, "insert", fake_insert)
    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)

    task = await tasks_service.create_task(
        project_id=str(project_id),
        title="Write docs",
        priority="high",
        actor="tester",
        role=Role.ADMIN,
    )
    assert task.title == "Write docs"
    assert task.status == "todo"
    assert task.priority == "high"


async def test_create_task_idempotent_replay_returns_existing_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid.uuid4()
    existing_task_id = uuid.uuid4()
    existing_task = FakeTask(id=existing_task_id, project_id=project_id, title="Original")
    prior_log = FakeAuditLog(
        tool_name="create_task",
        arguments={"idempotency_key": "abc123", "result_task_id": str(existing_task_id)},
    )

    async def fake_find_by_key(
        session: object, *, tool_name: str, idempotency_key: str
    ) -> FakeAuditLog:
        assert tool_name == "create_task"
        assert idempotency_key == "abc123"
        return prior_log

    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> FakeTask:
        assert task_id == existing_task_id
        return existing_task

    insert_calls: list[object] = []

    def fake_insert(session: object, task: object) -> None:
        insert_calls.append(task)

    monkeypatch.setattr(tasks_service.idempotency, "find_successful_call_by_key", fake_find_by_key)
    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(tasks_service.tasks_repository, "insert", fake_insert)

    result = await tasks_service.create_task(
        project_id=str(project_id),
        title="Ignored on replay",
        idempotency_key="abc123",
        actor="tester",
        role=Role.ADMIN,
    )

    assert result.id == str(existing_task_id)
    assert result.title == "Original"
    assert insert_calls == []  # no duplicate row inserted


async def test_create_task_no_prior_idempotency_key_creates_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid.uuid4()
    created: dict[str, FakeTask] = {}

    async def fake_find_by_key(session: object, *, tool_name: str, idempotency_key: str) -> None:
        return None

    async def fake_exists(session: object, pid: uuid.UUID) -> bool:
        return True

    def fake_insert(session: object, task: object) -> None:
        created["task"] = task  # type: ignore[assignment]

    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> FakeTask:
        return created["task"]

    monkeypatch.setattr(tasks_service.idempotency, "find_successful_call_by_key", fake_find_by_key)
    monkeypatch.setattr(tasks_service.projects_repository, "exists", fake_exists)
    monkeypatch.setattr(tasks_service.tasks_repository, "insert", fake_insert)
    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)

    task = await tasks_service.create_task(
        project_id=str(project_id),
        title="Fresh task",
        idempotency_key="new-key",
        actor="tester",
        role=Role.ADMIN,
    )
    assert task.title == "Fresh task"


# --- update_task / complete_task ----------------------------------------


async def test_update_task_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await tasks_service.update_task(
            task_id=str(uuid.uuid4()), title="x", actor="tester", role=Role.ADMIN
        )


async def test_update_task_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        await tasks_service.update_task(
            task_id=str(uuid.uuid4()), status="nonsense", actor="tester", role=Role.ADMIN
        )


async def test_update_task_blocked_requires_blocked_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    task = FakeTask(id=uuid.uuid4(), project_id=uuid.uuid4(), title="T")

    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> FakeTask:
        return task

    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(ValidationError):
        await tasks_service.update_task(
            task_id=str(task.id), status="blocked", actor="tester", role=Role.ADMIN
        )


async def test_update_task_blocked_with_reason_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    task = FakeTask(id=uuid.uuid4(), project_id=uuid.uuid4(), title="T")

    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> FakeTask:
        return task

    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)

    result = await tasks_service.update_task(
        task_id=str(task.id),
        status="blocked",
        blocked_reason="waiting on review",
        actor="tester",
        role=Role.ADMIN,
    )
    assert result.status == "blocked"
    assert result.blocked_reason == "waiting on review"


async def test_update_task_leaving_blocked_clears_blocked_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = FakeTask(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        title="T",
        status="blocked",
        blocked_reason="waiting",
    )

    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> FakeTask:
        return task

    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)

    result = await tasks_service.update_task(
        task_id=str(task.id), status="in_progress", actor="tester", role=Role.ADMIN
    )
    assert result.status == "in_progress"
    assert result.blocked_reason is None


async def test_complete_task_marks_done_and_audits_under_its_own_tool_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = FakeTask(id=uuid.uuid4(), project_id=uuid.uuid4(), title="T", status="in_progress")
    recorded: dict[str, object] = {}

    async def fake_get_by_id(session: object, task_id: uuid.UUID) -> FakeTask:
        return task

    async def fake_record_audit_event(session: object, **kwargs: object) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr(tasks_service.tasks_repository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(tasks_service, "record_audit_event", fake_record_audit_event)

    result = await tasks_service.complete_task(
        task_id=str(task.id), actor="tester", role=Role.ADMIN
    )

    assert result.status == "done"
    assert recorded["tool_name"] == "complete_task"
    assert recorded["actor"] == "tester"
    # Phase 6: admin bypass is visible in the audit row.
    assert recorded["arguments"]["approval_bypassed_by_admin"] is True  # type: ignore[index]


# --- Phase 6: approval gate (devbrain_common.approvals) ---------------------


async def test_create_task_user_without_approval_raises_approval_required() -> None:
    """`enforce_approval` raises before the idempotency/project lookups —
    no repository call needs mocking for this branch."""
    with pytest.raises(ApprovalRequiredError):
        await tasks_service.create_task(
            project_id=str(uuid.uuid4()),
            title="Needs approval",
            actor="user-bob",
            role=Role.USER,
            approval_id=None,
        )


async def test_update_task_user_without_approval_raises_approval_required() -> None:
    with pytest.raises(ApprovalRequiredError):
        await tasks_service.update_task(
            task_id=str(uuid.uuid4()),
            title="x",
            actor="user-bob",
            role=Role.USER,
            approval_id=None,
        )


async def test_complete_task_user_without_approval_raises_approval_required() -> None:
    with pytest.raises(ApprovalRequiredError):
        await tasks_service.complete_task(
            task_id=str(uuid.uuid4()), actor="user-bob", role=Role.USER, approval_id=None
        )
