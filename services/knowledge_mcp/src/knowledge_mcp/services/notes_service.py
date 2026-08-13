"""Note CRUD business logic.

Security note (ORCHESTRATION.md / second-brain-mcp-plan.md §5 / this
phase's task brief): `content_md` is always treated as opaque text data —
we only ever *read* it with a regex to find `[[wikilink]]` markup and feed
it to the embedding model. Nothing in this module ever `eval`s/`exec`s note
content or passes it to a shell. This matters concretely for the Phase 2
seeded note at `slug == "prompt-injection-fixture-01"`
(`scripts/generators/notes.py::PROMPT_INJECTION_SLUG`), whose `content`
contains an instruction-shaped payload — this module reads/searches/embeds
it exactly like any other note and never acts on its text.

Human-in-the-loop approval (DevBrain_vision.md §9/§10, gap closed post-
Phase-6 — see `risk.py`'s module docstring and PROGRESS_REPORT.md's Phase 6
addendum): `create_note`/`update_note` are medium-risk writes gated by
`devbrain_common.approvals.enforce_approval`, exactly like every other
service's medium-risk writes (`Role.ADMIN` bypasses, flagged
`approval_bypassed_by_admin=true` in the audit row; `Role.USER` must supply
a valid `approval_id`). `delete_note` is high-risk: `_enforce_high_risk_approval`
below deliberately does *not* reuse `enforce_approval`'s admin-bypass —
it requires `Role.ADMIN` **and** a valid, matching, unconsumed `approval_id`
unconditionally, per `risk.py`'s documented rationale.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from devbrain_common.approvals import consume_approval, enforce_approval
from devbrain_common.audit import record_audit_event
from devbrain_common.auth import Role
from devbrain_common.config import get_settings
from devbrain_common.errors import (
    ApprovalRequiredError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from devbrain_common.models import Embedding, Link, Note
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_mcp.repositories import links_repository as links_repository
from knowledge_mcp.repositories import notes_repository as notes_repository
from knowledge_mcp.repositories import unit_of_work as uow
from knowledge_mcp.services import embeddings as embeddings

NOTE_TYPES = ("learning", "architecture", "technical", "idea", "personal")

# `[[Target Title]]` or `[[Target Title|display text]]` — capture group 1 is
# always the target note's title. Never interpreted as anything but a
# literal string to look up; see module docstring.
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


@dataclass(frozen=True)
class NoteDTO:
    id: str
    project_id: str | None
    title: str
    slug: str
    content: str
    type: str
    tags: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


def note_to_dto(note: Note) -> NoteDTO:
    return NoteDTO(
        id=str(note.id),
        project_id=str(note.project_id) if note.project_id else None,
        title=note.title,
        slug=note.slug,
        content=note.content,
        type=note.type,
        tags=sorted(nt.tag.name for nt in note.note_tags),
        created_at=note.created_at,
        updated_at=note.updated_at,
        deleted_at=note.deleted_at,
    )


def slugify(title: str) -> str:
    """Pure, DB-free slug computation — unit-testable without Postgres."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "note"


def parse_wikilink_titles(content: str) -> list[str]:
    """Extract the literal target titles from `[[wikilinks]]` in `content`.

    Pure text parsing — never executes anything found in `content`. Titles
    are deduplicated case-insensitively, order preserved.
    """
    seen: dict[str, str] = {}
    for match in _WIKILINK_RE.finditer(content):
        title = match.group(1).strip()
        if title and title.lower() not in seen:
            seen[title.lower()] = title
    return list(seen.values())


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError(f"{field_name!r} is not a valid UUID: {value!r}") from exc


async def _unique_slug(session: AsyncSession, base_title: str) -> str:
    base = slugify(base_title)
    candidate = base
    suffix = 2
    while await notes_repository.slug_exists(session, candidate):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


async def _relink_wikilinks(session: AsyncSession, note: Note) -> None:
    """Recompute `Link` rows for `note` from its current `content`.

    Only links to titles that resolve to an existing note are created —
    unresolved `[[...]]` mentions are left as plain text, exactly like the
    Phase 2 seeder's convention (links are always referentially real rows,
    never parsed live out of markdown at read time).
    """
    await links_repository.delete_outgoing_for_note(session, note.id)
    for title in parse_wikilink_titles(note.content):
        target = await notes_repository.get_by_title(session, title)
        if target is None or target.id == note.id:
            continue
        links_repository.insert(
            session,
            Link(
                id=uuid.uuid4(),
                source_note_id=note.id,
                target_note_id=target.id,
                context_snippet=f"[[{title}]]",
            ),
        )


async def _reembed(session: AsyncSession, note: Note) -> None:
    await notes_repository.delete_embeddings_for_note(session, note.id)
    model_name = get_settings().embedding_model
    text = embeddings.note_embedding_text(note.title, note.content)
    vector = embeddings.encode_text(text, model_name)
    notes_repository.insert_embedding(
        session,
        Embedding(id=uuid.uuid4(), note_id=note.id, vector=vector, model_name=model_name),
    )


async def create_note(
    *,
    title: str,
    content_md: str,
    tags: list[str] | None = None,
    project_id: str | None = None,
    note_type: str = "technical",
    actor: str,
    role: Role,
    approval_id: str | None = None,
) -> NoteDTO:
    if not title.strip():
        raise ValidationError("title must not be empty.")
    if not content_md.strip():
        raise ValidationError("content_md must not be empty.")
    if note_type not in NOTE_TYPES:
        raise ValidationError(f"type must be one of {NOTE_TYPES}.")

    call_arguments: dict[str, Any] = {
        "title": title,
        "content_md": content_md,
        "tags": tags or [],
        "project_id": project_id,
        "note_type": note_type,
    }

    started = time.monotonic()
    async with uow.unit_of_work() as session:
        # Gap closed post-Phase-6 (see risk.py/module docstring): medium-risk
        # gate, identical shape to task_mcp/project_mcp/calendar_mcp.
        bypassed_as_admin = await enforce_approval(
            session,
            role=role,
            actor=actor,
            tool_name="notes.create",
            arguments=call_arguments,
            approval_id=approval_id,
        )

        slug = await _unique_slug(session, title)
        note = Note(
            id=uuid.uuid4(),
            project_id=_parse_uuid(project_id, "project_id") if project_id else None,
            title=title.strip(),
            slug=slug,
            content=content_md,
            type=note_type,
        )
        notes_repository.insert(session, note)
        await session.flush()

        tag_rows = await notes_repository.get_or_create_tags(session, tags or [])
        await notes_repository.replace_note_tags(session, note.id, tag_rows)
        await session.flush()

        await _relink_wikilinks(session, note)
        await _reembed(session, note)

        await record_audit_event(
            session,
            actor=actor,
            tool_name="notes.create",
            arguments={
                "title": title,
                "tags": tags or [],
                "type": note_type,
                "approval_id": approval_id,
                "approval_bypassed_by_admin": bypassed_as_admin,
            },
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        # Re-fetch with the `note_tags -> tag` eager-load chain populated
        # (the in-memory `note` object's `note_tags` collection was never
        # hydrated by the raw repository inserts above).
        persisted = await notes_repository.get_by_id(session, note.id)
        assert persisted is not None  # noqa: S101 - just inserted, in the same transaction
        return note_to_dto(persisted)


async def list_recent_notes(*, since_days: int = 7, limit: int = 100) -> list[NoteDTO]:
    """Notes created in the last `since_days` days, newest first.

    Phase 7 addition — see `repositories/notes_repository.py::list_since`'s
    docstring and PROGRESS_REPORT.md Phase 7 "Decisions made" for why this
    exists: `backend/src/devbrain_backend/agents/weekly_digest.py` needs a
    pure date-range listing that no pre-existing query-required search
    function can express.
    """
    if since_days < 1:
        raise ValidationError("since_days must be at least 1.")
    since = datetime.now(tz=UTC) - timedelta(days=since_days)
    async with uow.unit_of_work() as session:
        notes = await notes_repository.list_since(session, since, limit=limit)
        return [note_to_dto(n) for n in notes]


async def get_note(*, note_id: str | None = None, slug: str | None = None) -> NoteDTO:
    if not note_id and not slug:
        raise ValidationError("Provide either `id` or `slug`.")
    async with uow.unit_of_work() as session:
        note = None
        if note_id:
            note = await notes_repository.get_by_id(session, _parse_uuid(note_id, "note_id"))
        elif slug:
            note = await notes_repository.get_by_slug(session, slug)
        if note is None:
            raise NotFoundError("Note not found.")
        return note_to_dto(note)


async def update_note(
    *,
    note_id: str,
    title: str | None = None,
    content_md: str | None = None,
    tags: list[str] | None = None,
    note_type: str | None = None,
    actor: str,
    role: Role,
    approval_id: str | None = None,
) -> NoteDTO:
    if note_type is not None and note_type not in NOTE_TYPES:
        raise ValidationError(f"type must be one of {NOTE_TYPES}.")

    call_arguments: dict[str, Any] = {
        "note_id": note_id,
        "title": title,
        "content_md": content_md,
        "tags": tags,
        "note_type": note_type,
    }

    started = time.monotonic()
    async with uow.unit_of_work() as session:
        # Gap closed post-Phase-6 — see create_note's comment above for the
        # admin-bypass / user-needs-approval_id shape.
        bypassed_as_admin = await enforce_approval(
            session,
            role=role,
            actor=actor,
            tool_name="notes.update",
            arguments=call_arguments,
            approval_id=approval_id,
        )

        note = await notes_repository.get_by_id(session, _parse_uuid(note_id, "note_id"))
        if note is None:
            raise NotFoundError("Note not found.")

        content_changed = False
        if title is not None and title.strip():
            note.title = title.strip()
        if content_md is not None and content_md.strip():
            note.content = content_md
            content_changed = True
        if note_type is not None:
            note.type = note_type
        if tags is not None:
            tag_rows = await notes_repository.get_or_create_tags(session, tags)
            await notes_repository.replace_note_tags(session, note.id, tag_rows)
            await session.flush()

        if content_changed:
            await _relink_wikilinks(session, note)
            await _reembed(session, note)

        await record_audit_event(
            session,
            actor=actor,
            tool_name="notes.update",
            arguments={
                "note_id": note_id,
                "title_changed": title is not None,
                "content_changed": content_changed,
                "tags_changed": tags is not None,
                "approval_id": approval_id,
                "approval_bypassed_by_admin": bypassed_as_admin,
            },
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        persisted = await notes_repository.get_by_id(session, note.id)
        assert persisted is not None  # noqa: S101 - just fetched, in the same transaction
        return note_to_dto(persisted)


async def _enforce_high_risk_approval(
    session: AsyncSession,
    *,
    role: Role,
    actor: str,
    tool_name: str,
    arguments: dict[str, Any],
    approval_id: str | None,
) -> None:
    """The gate `notes.delete` (this service's one `RiskTier.HIGH` tool)
    calls right before mutating anything — deliberately **not** a call to
    `devbrain_common.approvals.enforce_approval`, whose `Role.ADMIN` bypass
    is exactly the "either/or" shortcut high risk must not get (see
    `risk.py`'s module docstring for the `DevBrain_vision.md` §10/§12
    citation backing this). Requires `Role.ADMIN` **and** a valid, matching,
    unconsumed `approval_id` — either one missing raises before any row is
    touched: `ForbiddenError` if the caller isn't admin (checked first, no
    DB access), `ApprovalRequiredError` if no `approval_id` was supplied
    (also no DB access) or `consume_approval` rejects it.
    """
    if not role.at_least(Role.ADMIN):
        raise ForbiddenError(
            f"Tool {tool_name!r} is high-risk and requires Role.ADMIN "
            f"(caller role was {role.value!r})."
        )
    if not approval_id:
        raise ApprovalRequiredError(
            f"Tool {tool_name!r} is high-risk and requires a valid approval_id "
            "even for Role.ADMIN callers. Call request_approval with the exact "
            "same arguments first."
        )
    await consume_approval(
        session, approval_id=approval_id, tool_name=tool_name, arguments=arguments
    )


async def delete_note(
    *, note_id: str, actor: str, role: Role, approval_id: str | None = None
) -> None:
    call_arguments: dict[str, Any] = {"note_id": note_id}

    started = time.monotonic()
    async with uow.unit_of_work() as session:
        await _enforce_high_risk_approval(
            session,
            role=role,
            actor=actor,
            tool_name="notes.delete",
            arguments=call_arguments,
            approval_id=approval_id,
        )

        note = await notes_repository.get_by_id(session, _parse_uuid(note_id, "note_id"))
        if note is None:
            raise NotFoundError("Note not found.")
        if note.deleted_at is not None:
            raise ConflictError("Note is already deleted.")
        note.deleted_at = datetime.now(tz=UTC)

        await record_audit_event(
            session,
            actor=actor,
            tool_name="notes.delete",
            arguments={"note_id": note_id, "approval_id": approval_id},
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
