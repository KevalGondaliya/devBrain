"""`links_service.get_backlinks`/`get_graph` orchestration — repository mocked."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from _fakes import fake_unit_of_work
from devbrain_common.errors import NotFoundError, ValidationError
from knowledge_mcp.repositories import unit_of_work as uow
from knowledge_mcp.services import links_service


@dataclass
class FakeNote:
    id: uuid.UUID
    title: str
    slug: str


@dataclass
class FakeLink:
    source_note_id: uuid.UUID
    target_note_id: uuid.UUID
    context_snippet: str | None
    source_note: FakeNote | None = None
    target_note: FakeNote | None = None


@pytest.fixture(autouse=True)
def _patch_unit_of_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uow, "unit_of_work", fake_unit_of_work)


async def test_get_backlinks_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, note_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(links_service.notes_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await links_service.get_backlinks(note_id=str(uuid.uuid4()))


async def test_get_backlinks_invalid_uuid_raises_validation() -> None:
    with pytest.raises(ValidationError):
        await links_service.get_backlinks(note_id="not-a-uuid")


async def test_get_backlinks_returns_source_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    target_id = uuid.uuid4()
    source = FakeNote(id=uuid.uuid4(), title="Source Note", slug="source-note")

    async def fake_get_by_id(session: object, note_id: uuid.UUID) -> FakeNote:
        return FakeNote(id=target_id, title="Target", slug="target")

    async def fake_get_incoming(session: object, note_id: uuid.UUID) -> list[FakeLink]:
        return [
            FakeLink(
                source_note_id=source.id,
                target_note_id=target_id,
                context_snippet="See also [[Target]].",
                source_note=source,
            )
        ]

    monkeypatch.setattr(links_service.notes_repository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(links_service.links_repository, "get_incoming", fake_get_incoming)

    backlinks = await links_service.get_backlinks(note_id=str(target_id))
    assert len(backlinks) == 1
    assert backlinks[0].source_title == "Source Note"
    assert backlinks[0].context_snippet == "See also [[Target]]."


async def test_get_graph_rejects_out_of_range_depth() -> None:
    with pytest.raises(ValidationError):
        await links_service.get_graph(note_id=str(uuid.uuid4()), depth=0)
    with pytest.raises(ValidationError):
        await links_service.get_graph(note_id=str(uuid.uuid4()), depth=6)


async def test_get_graph_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, note_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(links_service.notes_repository, "get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await links_service.get_graph(note_id=str(uuid.uuid4()))


async def test_get_graph_one_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    root_id = uuid.uuid4()
    other_id = uuid.uuid4()
    root = FakeNote(id=root_id, title="Root", slug="root")
    other = FakeNote(id=other_id, title="Other", slug="other")

    async def fake_get_by_id(session: object, note_id: uuid.UUID) -> FakeNote:
        return root

    async def fake_get_adjacent(session: object, note_ids: list[uuid.UUID]) -> list[FakeLink]:
        if root_id in note_ids:
            return [
                FakeLink(
                    source_note_id=root_id,
                    target_note_id=other_id,
                    context_snippet=None,
                    source_note=root,
                    target_note=other,
                )
            ]
        return []

    monkeypatch.setattr(links_service.notes_repository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(links_service.links_repository, "get_adjacent", fake_get_adjacent)

    graph = await links_service.get_graph(note_id=str(root_id), depth=2)
    node_ids = {n.note_id for n in graph.nodes}
    assert node_ids == {str(root_id), str(other_id)}
    assert len(graph.edges) == 1
    assert graph.edges[0].source_note_id == str(root_id)
    assert graph.edges[0].target_note_id == str(other_id)
