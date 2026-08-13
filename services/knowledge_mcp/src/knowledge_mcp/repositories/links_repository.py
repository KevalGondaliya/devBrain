"""Wikilink (`Link`) queries: no graph-traversal logic — see
`services/links_service.py` for BFS assembly over the adjacency this module
returns."""

from __future__ import annotations

import uuid

from devbrain_common.models import Link
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


def insert(session: AsyncSession, link: Link) -> None:
    session.add(link)


async def delete_outgoing_for_note(session: AsyncSession, note_id: uuid.UUID) -> None:
    stmt = select(Link).where(Link.source_note_id == note_id)
    result = await session.execute(stmt)
    for existing in result.scalars().all():
        await session.delete(existing)


async def get_outgoing(session: AsyncSession, note_id: uuid.UUID) -> list[Link]:
    stmt = (
        select(Link).options(selectinload(Link.target_note)).where(Link.source_note_id == note_id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_incoming(session: AsyncSession, note_id: uuid.UUID) -> list[Link]:
    stmt = (
        select(Link).options(selectinload(Link.source_note)).where(Link.target_note_id == note_id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_adjacent(session: AsyncSession, note_ids: list[uuid.UUID]) -> list[Link]:
    """Every link touching any of `note_ids` on either end, in one query —
    used by `links_service.get_graph` to expand one BFS frontier at a time."""
    if not note_ids:
        return []
    stmt = (
        select(Link)
        .options(selectinload(Link.source_note), selectinload(Link.target_note))
        .where(Link.source_note_id.in_(note_ids) | Link.target_note_id.in_(note_ids))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
