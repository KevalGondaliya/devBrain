"""Project queries: no business logic, no status-vocabulary validation — see
`services/projects_service.py`."""

from __future__ import annotations

import uuid

from devbrain_common.models import Project
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def _base_query() -> Select[tuple[Project]]:
    # `populate_existing=True` matters here: `projects_service.update_project_status`
    # mutates `project.status` then re-fetches within the same transaction —
    # without this, SQLAlchemy's identity map would hand back the same
    # in-memory object whose server-computed `updated_at` (onupdate=func.now())
    # is left in an *expired* state after `flush()`. Accessing an expired
    # attribute synchronously outside an explicit awaited refresh raises
    # `MissingGreenlet` under the async driver — the same class of bug
    # documented in knowledge_mcp/repositories/notes_repository.py's
    # `_base_query()`.
    return select(Project).execution_options(populate_existing=True)


async def get_by_id(session: AsyncSession, project_id: uuid.UUID) -> Project | None:
    stmt = _base_query().where(Project.id == project_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_all(session: AsyncSession, *, limit: int = 200) -> list[Project]:
    stmt = _base_query().order_by(Project.name).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def search(session: AsyncSession, query: str, limit: int) -> list[Project]:
    """`ILIKE` match on name/description."""
    pattern = f"%{query}%"
    stmt = (
        _base_query()
        .where(or_(Project.name.ilike(pattern), Project.description.ilike(pattern)))
        .order_by(Project.name)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
