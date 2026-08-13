"""Task queries: no business logic, no status-vocabulary validation — see
`services/tasks_service.py`."""

from __future__ import annotations

import uuid

from devbrain_common.models import Task
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def _base_query() -> Select[tuple[Task]]:
    # `populate_existing=True` matters here for the same reason documented in
    # `project_mcp/repositories/projects_repository.py::_base_query` (and,
    # originally, `knowledge_mcp/repositories/notes_repository.py`):
    # `tasks_service.update_task`/`create_task` re-fetch within the same
    # transaction after a write, and the server-computed `updated_at`
    # (onupdate=func.now()) is left expired after `flush()` — an unrefreshed
    # read would hit `MissingGreenlet` under the async driver.
    return select(Task).execution_options(populate_existing=True)


async def get_by_id(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    stmt = _base_query().where(Task.id == task_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_filters(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[Task]:
    stmt = _base_query()
    if project_id is not None:
        stmt = stmt.where(Task.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(Task.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def search(session: AsyncSession, query: str, limit: int) -> list[Task]:
    """`ILIKE` match on title/description."""
    pattern = f"%{query}%"
    stmt = (
        _base_query()
        .where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
        .order_by(Task.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def insert(session: AsyncSession, task: Task) -> None:
    session.add(task)
