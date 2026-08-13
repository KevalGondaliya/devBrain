"""Meeting queries (read-only — Knowledge MCP does not write meetings)."""

from __future__ import annotations

import uuid

from devbrain_common.models import Meeting
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_by_id(session: AsyncSession, meeting_id: uuid.UUID) -> Meeting | None:
    result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
    return result.scalar_one_or_none()


async def search(session: AsyncSession, query: str, limit: int) -> list[Meeting]:
    pattern = f"%{query}%"
    stmt = (
        select(Meeting)
        .where(or_(Meeting.title.ilike(pattern), Meeting.summary.ilike(pattern)))
        .order_by(Meeting.date.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
