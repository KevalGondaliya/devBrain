"""Decision queries (read-only — Knowledge MCP does not write decisions)."""

from __future__ import annotations

import uuid

from devbrain_common.models import Decision
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_by_id(session: AsyncSession, decision_id: uuid.UUID) -> Decision | None:
    result = await session.execute(select(Decision).where(Decision.id == decision_id))
    return result.scalar_one_or_none()


async def search(session: AsyncSession, query: str, limit: int) -> list[Decision]:
    pattern = f"%{query}%"
    stmt = (
        select(Decision)
        .where(
            or_(
                Decision.title.ilike(pattern),
                Decision.decision.ilike(pattern),
                Decision.reasoning.ilike(pattern),
            )
        )
        .order_by(Decision.date.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
