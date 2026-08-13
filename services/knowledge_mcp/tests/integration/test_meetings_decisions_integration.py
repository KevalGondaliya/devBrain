"""`search_meetings`/`read_meeting`/`search_decisions`/`get_decision` against
real seeded data (DevBrain_vision.md §11.1)."""

from __future__ import annotations

import pytest
from devbrain_common.models import Meeting
from knowledge_mcp.services import decisions_service, meetings_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("patched_uow")


async def test_search_and_read_meeting(db_session: AsyncSession) -> None:
    result = await db_session.execute(select(Meeting).limit(1))
    seeded = result.scalar_one()
    query_term = seeded.title.split()[0]

    hits = await meetings_service.search_meetings(query=query_term, limit=50)
    assert any(m.id == str(seeded.id) for m in hits)

    fetched = await meetings_service.read_meeting(meeting_id=str(seeded.id))
    assert fetched.title == seeded.title


async def test_search_and_get_decision_including_conflicting_pair(
    db_session: AsyncSession,
) -> None:
    # Phase 2 always injects a "Database choice" conflicting decision pair
    # (MongoDB superseded -> PostgreSQL accepted) — a stable search target.
    hits = await decisions_service.search_decisions(query="Database choice", limit=50)
    assert len(hits) >= 2
    statuses = {h.status for h in hits}
    assert "superseded" in statuses
    assert "accepted" in statuses

    fetched = await decisions_service.get_decision(decision_id=hits[0].id)
    assert fetched.id == hits[0].id
