"""`tags_service` — rename/cascade logic, repository layer mocked out."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from _fakes import fake_unit_of_work
from devbrain_common.auth import Role
from devbrain_common.errors import NotFoundError
from knowledge_mcp.repositories import unit_of_work as uow
from knowledge_mcp.services import tags_service


@dataclass
class FakeTag:
    id: uuid.UUID
    name: str


def test_normalize_tag_name_lowercases_and_strips() -> None:
    assert tags_service.normalize_tag_name("  MCP  ") == "mcp"


@pytest.fixture(autouse=True)
def _patch_unit_of_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uow, "unit_of_work", fake_unit_of_work)


async def test_rename_no_collision_just_renames(monkeypatch: pytest.MonkeyPatch) -> None:
    old_tag = FakeTag(id=uuid.uuid4(), name="oldname")
    renamed_calls = []

    async def fake_get_by_name(session: object, name: str) -> FakeTag | None:
        if name.strip().lower() == "oldname":
            return old_tag
        return None

    def fake_rename(tag: FakeTag, new_name: str) -> None:
        renamed_calls.append((tag, new_name))
        tag.name = new_name

    async def fake_list_all_with_counts(session: object) -> list[tuple[FakeTag, int]]:
        return [(old_tag, 3)]

    monkeypatch.setattr(tags_service.tags_repository, "get_by_name", fake_get_by_name)
    monkeypatch.setattr(tags_service.tags_repository, "rename", fake_rename)
    monkeypatch.setattr(
        tags_service.tags_repository, "list_all_with_counts", fake_list_all_with_counts
    )

    result = await tags_service.rename_tag(
        old_name="oldname", new_name="newname", actor="tester", role=Role.ADMIN
    )

    assert renamed_calls == [(old_tag, "newname")]
    assert result.name == "newname"
    assert result.note_count == 3


async def test_rename_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_name(session: object, name: str) -> FakeTag | None:
        return None

    monkeypatch.setattr(tags_service.tags_repository, "get_by_name", fake_get_by_name)

    with pytest.raises(NotFoundError):
        await tags_service.rename_tag(
            old_name="missing", new_name="whatever", actor="tester", role=Role.ADMIN
        )


async def test_rename_collision_cascades_and_deletes_old_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Renaming into an existing tag's name must repoint every note_tags row
    from the old tag to the existing target tag, then delete the now-empty
    old tag — the "cascade" this module's docstring describes."""
    old_tag = FakeTag(id=uuid.uuid4(), name="python")
    existing_target = FakeTag(id=uuid.uuid4(), name="py")

    repoint_calls = []
    delete_calls = []

    async def fake_get_by_name(session: object, name: str) -> FakeTag | None:
        normalized = name.strip().lower()
        if normalized == "python":
            return old_tag
        if normalized == "py":
            return existing_target
        return None

    async def fake_repoint_note_tags(session: object, from_id: uuid.UUID, to_id: uuid.UUID) -> None:
        repoint_calls.append((from_id, to_id))

    async def fake_delete_tag(session: object, tag: FakeTag) -> None:
        delete_calls.append(tag)

    async def fake_list_all_with_counts(session: object) -> list[tuple[FakeTag, int]]:
        return [(existing_target, 7)]

    monkeypatch.setattr(tags_service.tags_repository, "get_by_name", fake_get_by_name)
    monkeypatch.setattr(tags_service.tags_repository, "repoint_note_tags", fake_repoint_note_tags)
    monkeypatch.setattr(tags_service.tags_repository, "delete_tag", fake_delete_tag)
    monkeypatch.setattr(
        tags_service.tags_repository, "list_all_with_counts", fake_list_all_with_counts
    )

    result = await tags_service.rename_tag(
        old_name="python", new_name="py", actor="tester", role=Role.ADMIN
    )

    assert repoint_calls == [(old_tag.id, existing_target.id)]
    assert delete_calls == [old_tag]
    assert result.name == "py"
    assert result.note_count == 7


async def test_rename_to_same_name_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    old_tag = FakeTag(id=uuid.uuid4(), name="mcp")

    async def fake_get_by_name(session: object, name: str) -> FakeTag | None:
        return old_tag if name.strip().lower() == "mcp" else None

    async def fake_list_all_with_counts(session: object) -> list[tuple[FakeTag, int]]:
        return [(old_tag, 2)]

    monkeypatch.setattr(tags_service.tags_repository, "get_by_name", fake_get_by_name)
    monkeypatch.setattr(
        tags_service.tags_repository, "list_all_with_counts", fake_list_all_with_counts
    )

    result = await tags_service.rename_tag(
        old_name="mcp", new_name="MCP", actor="tester", role=Role.ADMIN
    )
    assert result.name == "mcp"
    assert result.note_count == 2
