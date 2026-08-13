"""Note queries: no business logic, no ranking decisions — see `services/`."""

from __future__ import annotations

import uuid
from datetime import datetime

from devbrain_common.models import Embedding, Note, NoteTag, Tag
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


def _base_query(*, include_deleted: bool = False) -> Select[tuple[Note]]:
    # `populate_existing()` matters here: services re-fetch a note (e.g.
    # `notes_service.update_note`) within the *same* session/transaction
    # after mutating its `note_tags` via `replace_note_tags` — without this,
    # SQLAlchemy's identity map would hand back the already-loaded (now
    # stale) `note_tags` collection instead of the freshly-committed rows,
    # since a plain re-`select()` does not refresh already-populated
    # relationships on an object already tracked by the session.
    stmt = (
        select(Note)
        .options(selectinload(Note.note_tags).selectinload(NoteTag.tag))
        .execution_options(populate_existing=True)
    )
    if not include_deleted:
        stmt = stmt.where(Note.deleted_at.is_(None))
    return stmt


async def get_by_id(
    session: AsyncSession, note_id: uuid.UUID, *, include_deleted: bool = False
) -> Note | None:
    stmt = _base_query(include_deleted=include_deleted).where(Note.id == note_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_slug(
    session: AsyncSession, slug: str, *, include_deleted: bool = False
) -> Note | None:
    stmt = _base_query(include_deleted=include_deleted).where(Note.slug == slug)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_title(session: AsyncSession, title: str) -> Note | None:
    """Case-insensitive exact title match — used to resolve `[[wikilinks]]`."""
    stmt = _base_query().where(func.lower(Note.title) == title.lower())
    result = await session.execute(stmt)
    return result.scalars().first()


async def slug_exists(session: AsyncSession, slug: str) -> bool:
    stmt = select(func.count()).select_from(Note).where(Note.slug == slug)
    result = await session.execute(stmt)
    return bool(result.scalar_one())


async def list_by_ids(session: AsyncSession, note_ids: list[uuid.UUID]) -> list[Note]:
    if not note_ids:
        return []
    stmt = _base_query().where(Note.id.in_(note_ids))
    result = await session.execute(stmt)
    return list(result.scalars().all())


def insert(session: AsyncSession, note: Note) -> None:
    session.add(note)


async def list_since(session: AsyncSession, since: datetime, limit: int = 100) -> list[Note]:
    """Notes created on or after `since`, newest first.

    Phase 7 addition (purely additive — no existing function's signature or
    behavior changed): `weekly_digest`'s literal spec (second-brain-mcp-plan.md
    §4 / DevBrain_vision.md) is "pulls notes from the last 7 days", and no
    existing read primitive (`search_keyword`/`search_semantic`, both
    query-required) can express a pure date-range listing. See
    PROGRESS_REPORT.md Phase 7 "Decisions made" for why this one function was
    added despite Phase 7's general "don't modify the five services" scope
    note.
    """
    stmt = _base_query().where(Note.created_at >= since)
    stmt = stmt.order_by(Note.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


async def search_keyword(session: AsyncSession, query: str, limit: int) -> list[tuple[Note, bool]]:
    """`ILIKE` match on title/content.

    Returns `(note, title_matched)` pairs so the service layer can weight
    title hits above body-only hits without this repository making that
    ranking decision itself.
    """
    pattern = f"%{query}%"
    stmt = (
        _base_query()
        .where(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
        .limit(limit)
    )
    result = await session.execute(stmt)
    notes = result.scalars().unique().all()
    return [(note, query.lower() in note.title.lower()) for note in notes]


async def search_semantic(
    session: AsyncSession, query_vector: list[float], limit: int
) -> list[tuple[Note, float]]:
    """Nearest neighbours by cosine distance against `embeddings.vector`.

    Returns `(note, cosine_distance)` pairs, ascending distance (closest
    first) — 0.0 is identical, 2.0 is maximally dissimilar.
    """
    distance = Embedding.vector.cosine_distance(query_vector)
    stmt = (
        select(Note, distance.label("distance"))
        .join(Embedding, Embedding.note_id == Note.id)
        .options(selectinload(Note.note_tags).selectinload(NoteTag.tag))
        .where(Note.deleted_at.is_(None))
        .order_by(distance)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(note, float(dist)) for note, dist in result.all()]


async def get_or_create_tags(session: AsyncSession, names: list[str]) -> list[Tag]:
    """Fetch existing tags by name, creating any that don't exist yet."""
    if not names:
        return []
    unique_names = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    if not unique_names:
        return []
    stmt = select(Tag).where(Tag.name.in_(unique_names))
    result = await session.execute(stmt)
    existing = {tag.name: tag for tag in result.scalars().all()}
    tags: list[Tag] = []
    for name in unique_names:
        tag = existing.get(name)
        if tag is None:
            tag = Tag(id=uuid.uuid4(), name=name)
            session.add(tag)
            existing[name] = tag
        tags.append(tag)
    return tags


async def replace_note_tags(session: AsyncSession, note_id: uuid.UUID, tags: list[Tag]) -> None:
    """Delete every existing `note_tags` row for `note_id`, then add fresh ones."""
    stmt = select(NoteTag).where(NoteTag.note_id == note_id)
    result = await session.execute(stmt)
    for existing in result.scalars().all():
        await session.delete(existing)
    await session.flush()
    for tag in tags:
        session.add(NoteTag(id=uuid.uuid4(), note_id=note_id, tag_id=tag.id))


def insert_embedding(session: AsyncSession, embedding: Embedding) -> None:
    session.add(embedding)


async def delete_embeddings_for_note(session: AsyncSession, note_id: uuid.UUID) -> None:
    stmt = select(Embedding).where(Embedding.note_id == note_id)
    result = await session.execute(stmt)
    for existing in result.scalars().all():
        await session.delete(existing)
