"""`notes_service` CRUD orchestration — repository/embeddings layers mocked."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from _fakes import fake_unit_of_work
from devbrain_common.auth import Role
from devbrain_common.errors import ConflictError, NotFoundError, ValidationError
from knowledge_mcp.repositories import unit_of_work as uow
from knowledge_mcp.services import notes_service


@dataclass
class FakeTag:
    id: uuid.UUID
    name: str


@dataclass
class FakeNoteTag:
    tag: FakeTag


@dataclass
class FakeNote:
    id: uuid.UUID
    title: str
    slug: str
    content: str
    type: str
    project_id: uuid.UUID | None = None
    note_tags: list[FakeNoteTag] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    deleted_at: datetime | None = None


@pytest.fixture(autouse=True)
def _patch_unit_of_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uow, "unit_of_work", fake_unit_of_work)


@pytest.fixture(autouse=True)
def _no_real_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_record_audit_event(session: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(notes_service, "record_audit_event", fake_record_audit_event)


@pytest.fixture(autouse=True)
def _stub_consume_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """`delete_note`'s high-risk gate always calls `consume_approval` (even
    for `Role.ADMIN` — see `notes_service._enforce_high_risk_approval`'s
    docstring), which would otherwise try a real `session.get(Approval, ...)`
    against the `FakeSession` these unit tests use. Tests that exercise the
    gate's own guard clauses (missing role/approval_id) never reach this
    call; tests that exercise unrelated soft-delete behavior pass a
    role=Role.ADMIN + approval_id and rely on this stub standing in for a
    real, already-approved approval (the actual gate logic is covered by
    `test_approval_gate.py`'s no-DB branches plus a real-Postgres
    integration test)."""

    async def fake_consume_approval(session: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(notes_service, "consume_approval", fake_consume_approval)


async def test_create_note_rejects_empty_title() -> None:
    with pytest.raises(ValidationError):
        await notes_service.create_note(
            title="  ", content_md="body", actor="tester", role=Role.ADMIN
        )


async def test_create_note_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        await notes_service.create_note(
            title="Title", content_md="   ", actor="tester", role=Role.ADMIN
        )


async def test_create_note_rejects_bad_type() -> None:
    with pytest.raises(ValidationError):
        await notes_service.create_note(
            title="Title",
            content_md="body",
            note_type="nonsense",
            actor="tester",
            role=Role.ADMIN,
        )


async def test_create_note_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    async def fake_slug_exists(session: object, slug: str) -> bool:
        return False

    def fake_insert(session: object, note: object) -> None:
        created["note"] = note

    async def fake_get_or_create_tags(session: object, names: list[str]) -> list[FakeTag]:
        # Mirrors notes_repository.get_or_create_tags' real normalization.
        return [FakeTag(id=uuid.uuid4(), name=n.strip().lower()) for n in names]

    async def fake_replace_note_tags(
        session: object, note_id: uuid.UUID, tags: list[FakeTag]
    ) -> None:
        created["tags"] = tags

    async def fake_get_by_id(
        session: object, note_id: uuid.UUID, include_deleted: bool = False
    ) -> FakeNote:
        real_note = created["note"]
        return FakeNote(
            id=real_note.id,
            title=real_note.title,
            slug=real_note.slug,
            content=real_note.content,
            type=real_note.type,
            project_id=real_note.project_id,
            note_tags=[FakeNoteTag(tag=t) for t in created.get("tags", [])],
        )

    async def fake_get_by_title(session: object, title: str) -> None:
        return None

    async def fake_delete_embeddings_for_note(session: object, note_id: uuid.UUID) -> None:
        return None

    def fake_insert_embedding(session: object, embedding: object) -> None:
        created["embedding"] = embedding

    async def fake_delete_outgoing_for_note(session: object, note_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(notes_service.notes_repository, "slug_exists", fake_slug_exists)
    monkeypatch.setattr(notes_service.notes_repository, "insert", fake_insert)
    monkeypatch.setattr(
        notes_service.notes_repository, "get_or_create_tags", fake_get_or_create_tags
    )
    monkeypatch.setattr(notes_service.notes_repository, "replace_note_tags", fake_replace_note_tags)
    monkeypatch.setattr(notes_service.notes_repository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(notes_service.notes_repository, "get_by_title", fake_get_by_title)
    monkeypatch.setattr(
        notes_service.notes_repository,
        "delete_embeddings_for_note",
        fake_delete_embeddings_for_note,
    )
    monkeypatch.setattr(notes_service.notes_repository, "insert_embedding", fake_insert_embedding)
    monkeypatch.setattr(
        notes_service.links_repository, "delete_outgoing_for_note", fake_delete_outgoing_for_note
    )
    monkeypatch.setattr(notes_service.embeddings, "encode_text", lambda text, model: [0.1, 0.2])

    note = await notes_service.create_note(
        title="My New Note",
        content_md="Some content.",
        tags=["MCP"],
        actor="tester",
        role=Role.ADMIN,
    )

    assert note.title == "My New Note"
    assert note.slug == "my-new-note"
    assert note.tags == ["mcp"]
    assert "embedding" in created


async def test_create_note_dedupes_slug_on_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_slug_exists(session: object, slug: str) -> bool:
        calls.append(slug)
        return slug == "my-note"

    def fake_insert(session: object, note: object) -> None:
        return None

    async def fake_get_or_create_tags(session: object, names: list[str]) -> list[FakeTag]:
        return []

    async def fake_replace_note_tags(
        session: object, note_id: uuid.UUID, tags: list[FakeTag]
    ) -> None:
        return None

    async def fake_get_by_id(
        session: object, note_id: uuid.UUID, include_deleted: bool = False
    ) -> FakeNote:
        return FakeNote(
            id=note_id, title="My Note", slug="my-note-2", content="x", type="technical"
        )

    async def fake_get_by_title(session: object, title: str) -> None:
        return None

    async def fake_delete_embeddings_for_note(session: object, note_id: uuid.UUID) -> None:
        return None

    def fake_insert_embedding(session: object, embedding: object) -> None:
        return None

    async def fake_delete_outgoing_for_note(session: object, note_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(notes_service.notes_repository, "slug_exists", fake_slug_exists)
    monkeypatch.setattr(notes_service.notes_repository, "insert", fake_insert)
    monkeypatch.setattr(
        notes_service.notes_repository, "get_or_create_tags", fake_get_or_create_tags
    )
    monkeypatch.setattr(notes_service.notes_repository, "replace_note_tags", fake_replace_note_tags)
    monkeypatch.setattr(notes_service.notes_repository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(notes_service.notes_repository, "get_by_title", fake_get_by_title)
    monkeypatch.setattr(
        notes_service.notes_repository,
        "delete_embeddings_for_note",
        fake_delete_embeddings_for_note,
    )
    monkeypatch.setattr(notes_service.notes_repository, "insert_embedding", fake_insert_embedding)
    monkeypatch.setattr(
        notes_service.links_repository, "delete_outgoing_for_note", fake_delete_outgoing_for_note
    )
    monkeypatch.setattr(notes_service.embeddings, "encode_text", lambda text, model: [0.1])

    await notes_service.create_note(
        title="My Note", content_md="body", actor="tester", role=Role.ADMIN
    )

    assert calls == ["my-note", "my-note-2"]


async def test_list_recent_notes_rejects_non_positive_since_days() -> None:
    with pytest.raises(ValidationError):
        await notes_service.list_recent_notes(since_days=0)


async def test_list_recent_notes_returns_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_notes = [
        FakeNote(id=uuid.uuid4(), title="Recent A", slug="recent-a", content="a", type="idea"),
        FakeNote(id=uuid.uuid4(), title="Recent B", slug="recent-b", content="b", type="technical"),
    ]
    seen: dict[str, object] = {}

    async def fake_list_since(session: object, since: datetime, limit: int = 100) -> list[FakeNote]:
        seen["since"] = since
        seen["limit"] = limit
        return fake_notes

    monkeypatch.setattr(notes_service.notes_repository, "list_since", fake_list_since)

    result = await notes_service.list_recent_notes(since_days=7, limit=50)

    assert [n.title for n in result] == ["Recent A", "Recent B"]
    assert seen["limit"] == 50
    # `since` should be ~7 days in the past, not in the future.
    assert seen["since"] < datetime.now(tz=UTC)


async def test_get_note_requires_id_or_slug() -> None:
    with pytest.raises(ValidationError):
        await notes_service.get_note()


async def test_get_note_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(
        session: object, note_id: uuid.UUID, include_deleted: bool = False
    ) -> None:
        return None

    monkeypatch.setattr(notes_service.notes_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await notes_service.get_note(note_id=str(uuid.uuid4()))


async def test_get_note_invalid_uuid_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        await notes_service.get_note(note_id="not-a-uuid")


async def test_get_note_by_slug_returns_dto(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_note = FakeNote(id=uuid.uuid4(), title="Found", slug="found", content="c", type="idea")

    async def fake_get_by_slug(
        session: object, slug: str, include_deleted: bool = False
    ) -> FakeNote:
        return fake_note

    monkeypatch.setattr(notes_service.notes_repository, "get_by_slug", fake_get_by_slug)

    result = await notes_service.get_note(slug="found")
    assert result.title == "Found"


async def test_delete_note_soft_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    note_id = uuid.uuid4()
    fake_note = FakeNote(id=note_id, title="T", slug="t", content="c", type="technical")

    async def fake_get_by_id(
        session: object, nid: uuid.UUID, include_deleted: bool = False
    ) -> FakeNote:
        return fake_note

    monkeypatch.setattr(notes_service.notes_repository, "get_by_id", fake_get_by_id)

    await notes_service.delete_note(
        note_id=str(note_id), actor="tester", role=Role.ADMIN, approval_id="approved-1"
    )
    assert fake_note.deleted_at is not None


async def test_delete_note_already_deleted_raises_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note_id = uuid.uuid4()
    fake_note = FakeNote(
        id=note_id,
        title="T",
        slug="t",
        content="c",
        type="technical",
        deleted_at=datetime.now(tz=UTC),
    )

    async def fake_get_by_id(
        session: object, nid: uuid.UUID, include_deleted: bool = False
    ) -> FakeNote:
        return fake_note

    monkeypatch.setattr(notes_service.notes_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(ConflictError):
        await notes_service.delete_note(
            note_id=str(note_id), actor="tester", role=Role.ADMIN, approval_id="approved-1"
        )


async def test_delete_note_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(
        session: object, nid: uuid.UUID, include_deleted: bool = False
    ) -> None:
        return None

    monkeypatch.setattr(notes_service.notes_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await notes_service.delete_note(
            note_id=str(uuid.uuid4()), actor="tester", role=Role.ADMIN, approval_id="approved-1"
        )
