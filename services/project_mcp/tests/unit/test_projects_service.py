"""`projects_service` orchestration — repository layer mocked."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from _project_mcp_fakes import fake_unit_of_work
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, NotFoundError, ValidationError
from project_mcp.repositories import unit_of_work as uow
from project_mcp.services import projects_service


@dataclass
class FakeProject:
    id: uuid.UUID
    name: str
    description: str | None = None
    status: str = "planned"
    priority: str | None = None
    start_date: datetime | None = None
    target_date: datetime | None = None
    owner: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@pytest.fixture(autouse=True)
def _patch_unit_of_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uow, "unit_of_work", fake_unit_of_work)


@pytest.fixture(autouse=True)
def _no_real_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_record_audit_event(session: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(projects_service, "record_audit_event", fake_record_audit_event)


async def test_list_projects_returns_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    projects = [
        FakeProject(id=uuid.uuid4(), name="Alpha"),
        FakeProject(id=uuid.uuid4(), name="Beta"),
    ]

    async def fake_list_all(session: object, limit: int = 200) -> list[FakeProject]:
        return projects

    monkeypatch.setattr(projects_service.projects_repository, "list_all", fake_list_all)

    result = await projects_service.list_projects()
    assert [p.name for p in result] == ["Alpha", "Beta"]


async def test_search_projects_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        await projects_service.search_projects(query="   ")


async def test_search_projects_returns_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    matched = [FakeProject(id=uuid.uuid4(), name="OAuth Revamp")]

    async def fake_search(session: object, query: str, limit: int) -> list[FakeProject]:
        assert query == "oauth"
        return matched

    monkeypatch.setattr(projects_service.projects_repository, "search", fake_search)

    result = await projects_service.search_projects(query="oauth")
    assert result[0].name == "OAuth Revamp"


async def test_get_project_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, project_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(projects_service.projects_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await projects_service.get_project(project_id=str(uuid.uuid4()))


async def test_get_project_invalid_uuid_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        await projects_service.get_project(project_id="not-a-uuid")


async def test_get_project_returns_dto(monkeypatch: pytest.MonkeyPatch) -> None:
    project = FakeProject(id=uuid.uuid4(), name="Found", status="active")

    async def fake_get_by_id(session: object, project_id: uuid.UUID) -> FakeProject:
        return project

    monkeypatch.setattr(projects_service.projects_repository, "get_by_id", fake_get_by_id)

    result = await projects_service.get_project(project_id=str(project.id))
    assert result.name == "Found"
    assert result.status == "active"


async def test_get_project_status_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, project_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(projects_service.projects_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await projects_service.get_project_status(project_id=str(uuid.uuid4()))


async def test_get_project_status_returns_status_dto(monkeypatch: pytest.MonkeyPatch) -> None:
    project = FakeProject(id=uuid.uuid4(), name="P", status="blocked", priority="high")

    async def fake_get_by_id(session: object, project_id: uuid.UUID) -> FakeProject:
        return project

    monkeypatch.setattr(projects_service.projects_repository, "get_by_id", fake_get_by_id)

    result = await projects_service.get_project_status(project_id=str(project.id))
    assert result.status == "blocked"
    assert result.priority == "high"


async def test_update_project_status_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        await projects_service.update_project_status(
            project_id=str(uuid.uuid4()), status="nonsense", actor="tester", role=Role.ADMIN
        )


async def test_update_project_status_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, project_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(projects_service.projects_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await projects_service.update_project_status(
            project_id=str(uuid.uuid4()), status="active", actor="tester", role=Role.ADMIN
        )


async def test_update_project_status_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    project = FakeProject(id=uuid.uuid4(), name="P", status="planned")

    async def fake_get_by_id(session: object, project_id: uuid.UUID) -> FakeProject:
        return project

    monkeypatch.setattr(projects_service.projects_repository, "get_by_id", fake_get_by_id)

    result = await projects_service.update_project_status(
        project_id=str(project.id),
        status="active",
        reason="kickoff",
        actor="tester",
        role=Role.ADMIN,
    )
    assert result.status == "active"
    assert project.status == "active"


async def test_update_project_status_audits_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    project = FakeProject(id=uuid.uuid4(), name="P", status="planned")
    recorded: dict[str, object] = {}

    async def fake_get_by_id(session: object, project_id: uuid.UUID) -> FakeProject:
        return project

    async def fake_record_audit_event(session: object, **kwargs: object) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr(projects_service.projects_repository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(projects_service, "record_audit_event", fake_record_audit_event)

    await projects_service.update_project_status(
        project_id=str(project.id),
        status="completed",
        reason="shipped",
        actor="tester",
        role=Role.ADMIN,
    )

    assert recorded["tool_name"] == "update_project_status"
    assert recorded["actor"] == "tester"
    assert recorded["arguments"]["status"] == "completed"  # type: ignore[index]
    assert recorded["arguments"]["reason"] == "shipped"  # type: ignore[index]
    # Phase 6: admin bypass is visible in the audit row.
    assert recorded["arguments"]["approval_bypassed_by_admin"] is True  # type: ignore[index]


async def test_update_project_status_user_without_approval_raises_approval_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`enforce_approval` raises before the project is even fetched — no
    repository call needs mocking for this branch."""
    with pytest.raises(ApprovalRequiredError):
        await projects_service.update_project_status(
            project_id=str(uuid.uuid4()),
            status="active",
            actor="user-bob",
            role=Role.USER,
            approval_id=None,
        )
