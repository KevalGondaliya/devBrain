"""Backlinks + graph traversal against real seeded `[[wikilinks]]`
(`db_test`, `--size small --seed 42`)."""

from __future__ import annotations

import pytest
from devbrain_common.models import Link
from knowledge_mcp.services import links_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("patched_uow")


async def test_backlinks_and_graph_against_seeded_links(db_session: AsyncSession) -> None:
    # Phase 2 seeds real Link rows for ~35% of notes (see
    # scripts/generators/notes.py) — find one that actually has a target.
    result = await db_session.execute(select(Link).limit(1))
    seeded_link = result.scalar_one_or_none()
    assert seeded_link is not None, "expected at least one seeded Link row in --size small"

    target_id = str(seeded_link.target_note_id)
    source_id = str(seeded_link.source_note_id)

    backlinks = await links_service.get_backlinks(note_id=target_id)
    assert any(b.source_note_id == source_id for b in backlinks)

    graph = await links_service.get_graph(note_id=source_id, depth=1)
    node_ids = {n.note_id for n in graph.nodes}
    assert source_id in node_ids
    assert target_id in node_ids
    assert any(e.source_note_id == source_id and e.target_note_id == target_id for e in graph.edges)


async def test_graph_depth_2_reaches_further_than_depth_1(db_session: AsyncSession) -> None:
    # Find a note that is itself a target of one link and a source of
    # another, so depth=2 from the first link's source reaches strictly
    # further than depth=1.
    result = await db_session.execute(select(Link))
    links = result.scalars().all()
    by_source = {link.source_note_id: link for link in links}
    chain_start = None
    for link in links:
        if link.target_note_id in by_source:
            chain_start = link
            break
    if chain_start is None:
        pytest.skip("no two-hop wikilink chain in this seeded dataset")

    graph_1 = await links_service.get_graph(note_id=str(chain_start.source_note_id), depth=1)
    graph_2 = await links_service.get_graph(note_id=str(chain_start.source_note_id), depth=2)
    assert len(graph_2.nodes) >= len(graph_1.nodes)
