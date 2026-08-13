"""`github_activities` queries: no business logic, no type-vocabulary
validation — see `adapters/fake_github.py` (the caller) and
`services/github_service.py`.

Only ever used by `FakeGithubAdapter` — this module is deliberately the
*only* place in this service that imports SQLAlchemy/`devbrain_common.models`,
so a future `RealGithubAdapter` swap touches nothing here.
"""

from __future__ import annotations

import uuid

from devbrain_common.models import GithubActivity
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def _base_query() -> Select[tuple[GithubActivity]]:
    return select(GithubActivity).execution_options(populate_existing=True)


async def get_by_id(session: AsyncSession, activity_id: uuid.UUID) -> GithubActivity | None:
    stmt = _base_query().where(GithubActivity.id == activity_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def search(
    session: AsyncSession, *, query: str, type_: str | None, limit: int
) -> list[GithubActivity]:
    """`ILIKE` match on title/repository/author, optionally restricted to
    one `type` (e.g. `"issue"`, `"commit"`)."""
    pattern = f"%{query}%"
    stmt = _base_query().where(
        or_(
            GithubActivity.title.ilike(pattern),
            GithubActivity.repository.ilike(pattern),
            GithubActivity.author.ilike(pattern),
        )
    )
    if type_ is not None:
        stmt = stmt.where(GithubActivity.type == type_)
    stmt = stmt.order_by(GithubActivity.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_by_filters(
    session: AsyncSession,
    *,
    repository: str | None = None,
    type_: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[GithubActivity]:
    stmt = _base_query()
    if repository is not None:
        stmt = stmt.where(GithubActivity.repository == repository)
    if type_ is not None:
        stmt = stmt.where(GithubActivity.type == type_)
    if status is not None:
        stmt = stmt.where(GithubActivity.status == status)
    stmt = stmt.order_by(GithubActivity.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
