"""Backlink/graph BFS traversal — pure function, no DB."""

from __future__ import annotations

import uuid

from knowledge_mcp.services.links_service import build_subgraph


def _uuids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def test_no_edges_visits_only_root() -> None:
    root = uuid.uuid4()
    visited, edges = build_subgraph(root, {}, depth=2)
    assert visited == {root}
    assert edges == set()


def test_one_hop_visits_direct_neighbor() -> None:
    a, b = _uuids(2)
    adjacency = {a: [(a, b)], b: [(a, b)]}
    visited, edges = build_subgraph(a, adjacency, depth=1)
    assert visited == {a, b}
    assert edges == {(a, b)}


def test_depth_limits_expansion() -> None:
    a, b, c = _uuids(3)
    # a -> b -> c chain
    adjacency = {
        a: [(a, b)],
        b: [(a, b), (b, c)],
        c: [(b, c)],
    }
    visited_depth1, _ = build_subgraph(a, adjacency, depth=1)
    assert visited_depth1 == {a, b}

    visited_depth2, edges_depth2 = build_subgraph(a, adjacency, depth=2)
    assert visited_depth2 == {a, b, c}
    assert edges_depth2 == {(a, b), (b, c)}


def test_incoming_edges_traversed_too() -> None:
    a, b = _uuids(2)
    # b links to a (incoming edge from a's perspective)
    adjacency = {a: [(b, a)], b: [(b, a)]}
    visited, edges = build_subgraph(a, adjacency, depth=1)
    assert visited == {a, b}
    assert edges == {(b, a)}


def test_cycle_does_not_infinite_loop() -> None:
    a, b = _uuids(2)
    adjacency = {a: [(a, b), (b, a)], b: [(a, b), (b, a)]}
    visited, edges = build_subgraph(a, adjacency, depth=5)
    assert visited == {a, b}
    assert edges == {(a, b), (b, a)}


def test_stops_early_when_frontier_exhausted() -> None:
    a, b = _uuids(2)
    adjacency = {a: [(a, b)], b: [(a, b)]}
    # depth=5 requested but the graph only has one hop worth of edges
    visited, edges = build_subgraph(a, adjacency, depth=5)
    assert visited == {a, b}
    assert edges == {(a, b)}


def test_isolated_root_with_deep_depth() -> None:
    root = uuid.uuid4()
    visited, edges = build_subgraph(root, {}, depth=5)
    assert visited == {root}
    assert edges == set()
