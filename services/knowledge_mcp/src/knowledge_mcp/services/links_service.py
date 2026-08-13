"""Backlinks + Obsidian-style subgraph traversal.

`build_subgraph` is the pure BFS core (no DB): given a root note id and an
adjacency map of `{note_id: [(other_note_id, direction)]}` edges, it
expands breadth-first up to `depth` hops and returns the visited node ids
plus deduplicated, direction-tagged edges. `get_graph` below is the thin
async wrapper that fetches adjacency one BFS frontier at a time via
`links_repository.get_adjacent` and feeds it to `build_subgraph`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from devbrain_common.errors import NotFoundError, ValidationError

from knowledge_mcp.repositories import links_repository as links_repository
from knowledge_mcp.repositories import notes_repository as notes_repository
from knowledge_mcp.repositories import unit_of_work as uow

Direction = Literal["outgoing", "incoming"]


@dataclass(frozen=True)
class BacklinkDTO:
    source_note_id: str
    source_title: str
    source_slug: str
    context_snippet: str | None


@dataclass(frozen=True)
class GraphEdge:
    source_note_id: str
    target_note_id: str


@dataclass(frozen=True)
class GraphNode:
    note_id: str
    title: str
    slug: str


@dataclass(frozen=True)
class GraphDTO:
    root_note_id: str
    depth: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def build_subgraph(
    root_id: uuid.UUID,
    adjacency: dict[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]],
    depth: int,
) -> tuple[set[uuid.UUID], set[tuple[uuid.UUID, uuid.UUID]]]:
    """Pure BFS: `adjacency[note_id]` is a list of `(source_id, target_id)`
    edges touching `note_id` (either direction). Returns
    `(visited_note_ids, deduplicated_edges)`.
    """
    visited: set[uuid.UUID] = {root_id}
    edges: set[tuple[uuid.UUID, uuid.UUID]] = set()
    frontier = {root_id}
    for _ in range(max(depth, 0)):
        next_frontier: set[uuid.UUID] = set()
        for note_id in frontier:
            for source_id, target_id in adjacency.get(note_id, []):
                edges.add((source_id, target_id))
                for other in (source_id, target_id):
                    if other not in visited:
                        visited.add(other)
                        next_frontier.add(other)
        if not next_frontier:
            break
        frontier = next_frontier
    return visited, edges


async def get_backlinks(*, note_id: str) -> list[BacklinkDTO]:
    async with uow.unit_of_work() as session:
        target_uuid = _parse_uuid(note_id)
        note = await notes_repository.get_by_id(session, target_uuid)
        if note is None:
            raise NotFoundError("Note not found.")
        incoming = await links_repository.get_incoming(session, target_uuid)
        return [
            BacklinkDTO(
                source_note_id=str(link.source_note_id),
                source_title=link.source_note.title,
                source_slug=link.source_note.slug,
                context_snippet=link.context_snippet,
            )
            for link in incoming
        ]


async def get_graph(*, note_id: str, depth: int = 2) -> GraphDTO:
    if depth < 1 or depth > 5:
        raise ValidationError("depth must be between 1 and 5.")
    async with uow.unit_of_work() as session:
        root_uuid = _parse_uuid(note_id)
        root = await notes_repository.get_by_id(session, root_uuid)
        if root is None:
            raise NotFoundError("Note not found.")

        adjacency: dict[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]] = {}
        titles: dict[uuid.UUID, tuple[str, str]] = {root_uuid: (root.title, root.slug)}
        frontier = {root_uuid}
        seen_frontiers: set[uuid.UUID] = {root_uuid}
        for _ in range(depth):
            links = await links_repository.get_adjacent(session, list(frontier))
            next_frontier: set[uuid.UUID] = set()
            for link in links:
                for endpoint_id, endpoint_note in (
                    (link.source_note_id, link.source_note),
                    (link.target_note_id, link.target_note),
                ):
                    adjacency.setdefault(endpoint_id, []).append(
                        (link.source_note_id, link.target_note_id)
                    )
                    titles.setdefault(endpoint_id, (endpoint_note.title, endpoint_note.slug))
                    if endpoint_id not in seen_frontiers:
                        next_frontier.add(endpoint_id)
            if not next_frontier:
                break
            seen_frontiers |= next_frontier
            frontier = next_frontier

        visited, edges = build_subgraph(root_uuid, adjacency, depth)
        return GraphDTO(
            root_note_id=str(root_uuid),
            depth=depth,
            nodes=[
                GraphNode(note_id=str(nid), title=titles[nid][0], slug=titles[nid][1])
                for nid in visited
                if nid in titles
            ],
            edges=[
                GraphEdge(source_note_id=str(s), target_note_id=str(t)) for s, t in sorted(edges)
            ],
        )


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError(f"note_id is not a valid UUID: {value!r}") from exc
