"""Tag listing + rename (with cascade merge).

Renaming a tag is a single `UPDATE tags SET name = ...` — every `note_tags`
row still points at the same `tag_id`, so the new name is visible on every
previously-tagged note "for free". The one real cascade case is a
**collision**: if `new_name` already exists as a different tag, every note
carrying the old tag must end up carrying the (pre-existing) new tag
instead, without violating `note_tags`'s `(note_id, tag_id)` uniqueness for
notes that already had both — `tags_repository.repoint_note_tags` handles
that de-duplication, and the now-empty old tag row is deleted.

Human-in-the-loop approval (gap closed post-Phase-6 — see
`knowledge_mcp/risk.py`'s module docstring and PROGRESS_REPORT.md's Phase 6
addendum): `rename_tag` is a medium-risk write gated by
`devbrain_common.approvals.enforce_approval`, same shape as every other
service's medium-risk writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from devbrain_common.approvals import enforce_approval
from devbrain_common.audit import record_audit_event
from devbrain_common.auth import Role
from devbrain_common.errors import NotFoundError, ValidationError

from knowledge_mcp.repositories import tags_repository as tags_repository
from knowledge_mcp.repositories import unit_of_work as uow


@dataclass(frozen=True)
class TagDTO:
    name: str
    note_count: int


def normalize_tag_name(name: str) -> str:
    """Pure normalization used consistently for lookups, storage, and
    rename targets — tags are always lowercase/stripped."""
    return name.strip().lower()


async def list_tags() -> list[TagDTO]:
    async with uow.unit_of_work() as session:
        rows = await tags_repository.list_all_with_counts(session)
        return [TagDTO(name=tag.name, note_count=count) for tag, count in rows]


async def rename_tag(
    *,
    old_name: str,
    new_name: str,
    actor: str,
    role: Role,
    approval_id: str | None = None,
) -> TagDTO:
    normalized_new = normalize_tag_name(new_name)
    if not normalized_new:
        raise ValidationError("new name must not be empty.")

    call_arguments: dict[str, Any] = {"old_name": old_name, "new_name": new_name}

    async with uow.unit_of_work() as session:
        # Gap closed post-Phase-6 (see risk.py/module docstring): medium-risk
        # gate, identical shape to task_mcp/project_mcp/calendar_mcp.
        bypassed_as_admin = await enforce_approval(
            session,
            role=role,
            actor=actor,
            tool_name="tags.rename",
            arguments=call_arguments,
            approval_id=approval_id,
        )

        old_tag = await tags_repository.get_by_name(session, old_name)
        if old_tag is None:
            raise NotFoundError(f"Tag {old_name!r} not found.")

        if normalize_tag_name(old_tag.name) == normalized_new:
            existing_counts = await tags_repository.list_all_with_counts(session)
            count = next((c for t, c in existing_counts if t.id == old_tag.id), 0)
            return TagDTO(name=old_tag.name, note_count=count)

        colliding_tag = await tags_repository.get_by_name(session, normalized_new)
        if colliding_tag is not None:
            await tags_repository.repoint_note_tags(session, old_tag.id, colliding_tag.id)
            await tags_repository.delete_tag(session, old_tag)
            target = colliding_tag
        else:
            tags_repository.rename(old_tag, normalized_new)
            target = old_tag

        await record_audit_event(
            session,
            actor=actor,
            tool_name="tags.rename",
            arguments={
                "old_name": old_name,
                "new_name": new_name,
                "approval_id": approval_id,
                "approval_bypassed_by_admin": bypassed_as_admin,
            },
            status="success",
        )

        counts = await tags_repository.list_all_with_counts(session)
        count = next((c for t, c in counts if t.id == target.id), 0)
        return TagDTO(name=target.name, note_count=count)
