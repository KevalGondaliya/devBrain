"""Project business logic: list/search/get/status, per
`DevBrain_vision.md` §11.2.

Security note (ORCHESTRATION.md): `name`/`description`/`reason` are always
treated as opaque text data — never `eval`/`exec`d or passed to a shell,
only ever persisted or ILIKE-matched.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from devbrain_common.approvals import enforce_approval
from devbrain_common.audit import record_audit_event
from devbrain_common.auth import Role
from devbrain_common.errors import NotFoundError, ValidationError
from devbrain_common.models import Project

from project_mcp.repositories import projects_repository as projects_repository
from project_mcp.repositories import unit_of_work as uow

PROJECT_STATUSES = ("planned", "active", "blocked", "completed", "archived")


@dataclass(frozen=True)
class ProjectDTO:
    id: str
    name: str
    description: str | None
    status: str
    priority: str | None
    start_date: datetime | None
    target_date: datetime | None
    owner: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ProjectStatusDTO:
    project_id: str
    status: str
    priority: str | None
    target_date: datetime | None
    updated_at: datetime | None = None


def project_to_dto(project: Project) -> ProjectDTO:
    return ProjectDTO(
        id=str(project.id),
        name=project.name,
        description=project.description,
        status=project.status,
        priority=project.priority,
        start_date=project.start_date,
        target_date=project.target_date,
        owner=project.owner,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError(f"{field_name!r} is not a valid UUID: {value!r}") from exc


async def list_projects() -> list[ProjectDTO]:
    async with uow.unit_of_work() as session:
        projects = await projects_repository.list_all(session)
        return [project_to_dto(p) for p in projects]


async def search_projects(*, query: str, limit: int = 20) -> list[ProjectDTO]:
    if not query.strip():
        raise ValidationError("query must not be empty.")
    async with uow.unit_of_work() as session:
        projects = await projects_repository.search(session, query, limit)
        return [project_to_dto(p) for p in projects]


async def get_project(*, project_id: str) -> ProjectDTO:
    async with uow.unit_of_work() as session:
        project = await projects_repository.get_by_id(session, _parse_uuid(project_id, "id"))
        if project is None:
            raise NotFoundError("Project not found.")
        return project_to_dto(project)


async def get_project_status(*, project_id: str) -> ProjectStatusDTO:
    async with uow.unit_of_work() as session:
        project = await projects_repository.get_by_id(session, _parse_uuid(project_id, "id"))
        if project is None:
            raise NotFoundError("Project not found.")
        return ProjectStatusDTO(
            project_id=str(project.id),
            status=project.status,
            priority=project.priority,
            target_date=project.target_date,
            updated_at=project.updated_at,
        )


async def update_project_status(
    *,
    project_id: str,
    status: str,
    reason: str | None = None,
    actor: str,
    role: Role,
    approval_id: str | None = None,
) -> ProjectDTO:
    if status not in PROJECT_STATUSES:
        raise ValidationError(f"status must be one of {PROJECT_STATUSES}.")

    call_arguments = {"project_id": project_id, "status": status, "reason": reason}

    started = time.monotonic()
    async with uow.unit_of_work() as session:
        # Phase 6 human-in-the-loop gate (devbrain_common.approvals):
        # Role.ADMIN bypasses (flagged in the audit row below); Role.USER
        # must supply a valid, matching, unconsumed approval_id or this
        # raises ApprovalRequiredError before anything is mutated.
        bypassed_as_admin = await enforce_approval(
            session,
            role=role,
            actor=actor,
            tool_name="update_project_status",
            arguments=call_arguments,
            approval_id=approval_id,
        )

        project = await projects_repository.get_by_id(session, _parse_uuid(project_id, "id"))
        if project is None:
            raise NotFoundError("Project not found.")

        previous_status = project.status
        project.status = status
        await session.flush()

        await record_audit_event(
            session,
            actor=actor,
            tool_name="update_project_status",
            arguments={
                **call_arguments,
                "previous_status": previous_status,
                "approval_id": approval_id,
                "approval_bypassed_by_admin": bypassed_as_admin,
            },
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        persisted = await projects_repository.get_by_id(session, project.id)
        assert persisted is not None  # noqa: S101 - just updated, in the same transaction
        return project_to_dto(persisted)
