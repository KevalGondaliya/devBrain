"""Tag queries: no business logic (renaming/merging decisions live in
`services/tags_service.py`)."""

from __future__ import annotations

import uuid

from devbrain_common.models import Note, NoteTag, Tag
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_by_name(session: AsyncSession, name: str) -> Tag | None:
    stmt = select(Tag).where(func.lower(Tag.name) == name.strip().lower())
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_all_with_counts(session: AsyncSession) -> list[tuple[Tag, int]]:
    """Every tag plus how many (non-deleted) notes carry it, name-sorted."""
    stmt = (
        select(Tag, func.count(NoteTag.id))
        .join(NoteTag, NoteTag.tag_id == Tag.id, isouter=True)
        .join(Note, (Note.id == NoteTag.note_id) & (Note.deleted_at.is_(None)), isouter=True)
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    result = await session.execute(stmt)
    return [(tag, count) for tag, count in result.all()]


async def repoint_note_tags(
    session: AsyncSession, from_tag_id: uuid.UUID, to_tag_id: uuid.UUID
) -> None:
    """Move every `note_tags` row from one tag to another, skipping rows that
    would collide with a `(note_id, tag_id)` pair already pointed at the
    target tag (a note already carrying both the old and new tag name)."""
    existing_targets_stmt = select(NoteTag.note_id).where(NoteTag.tag_id == to_tag_id)
    existing_targets = set((await session.execute(existing_targets_stmt)).scalars().all())

    stmt = select(NoteTag).where(NoteTag.tag_id == from_tag_id)
    result = await session.execute(stmt)
    for note_tag in result.scalars().all():
        if note_tag.note_id in existing_targets:
            await session.delete(note_tag)
        else:
            note_tag.tag_id = to_tag_id
    await session.flush()


def rename(tag: Tag, new_name: str) -> None:
    tag.name = new_name.strip().lower()


async def delete_tag(session: AsyncSession, tag: Tag) -> None:
    await session.delete(tag)
