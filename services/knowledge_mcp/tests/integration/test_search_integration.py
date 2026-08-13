"""Hybrid/keyword/semantic search against real seeded data (`db_test`,
`--size small --seed 42`)."""

from __future__ import annotations

import pytest
from knowledge_mcp.services import search_service

pytestmark = pytest.mark.usefixtures("patched_uow")

# A substring guaranteed to exist verbatim in the Phase 2 prompt-injection
# fixture note's *title* (see scripts/generators/notes.py) — a stable target
# regardless of dataset size/seed variability elsewhere.
FIXTURE_QUERY = "vendor security questionnaire"


async def test_keyword_search_finds_fixture_note_by_title() -> None:
    hits = await search_service.search_notes(query=FIXTURE_QUERY, mode="keyword", limit=10)
    assert any(h.note.slug == "prompt-injection-fixture-01" for h in hits)
    match = next(h for h in hits if h.note.slug == "prompt-injection-fixture-01")
    assert match.matched_via == "keyword"
    assert match.score == search_service.KEYWORD_TITLE_SCORE


async def test_semantic_search_finds_fixture_note_by_meaning() -> None:
    hits = await search_service.search_notes(
        query="vendor security review questionnaire follow up notes", mode="semantic", limit=10
    )
    assert any(h.note.slug == "prompt-injection-fixture-01" for h in hits)


async def test_hybrid_search_combines_both_modes() -> None:
    hits = await search_service.search_notes(query=FIXTURE_QUERY, mode="hybrid", limit=10)
    assert len(hits) > 0
    match = next((h for h in hits if h.note.slug == "prompt-injection-fixture-01"), None)
    assert match is not None
    # Matched by title text AND (very likely) by meaning -> "both".
    assert match.matched_via in ("both", "keyword")


async def test_search_results_are_score_sorted_descending() -> None:
    hits = await search_service.search_notes(query=FIXTURE_QUERY, mode="hybrid", limit=20)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


async def test_search_never_executes_fixture_note_content() -> None:
    """Searching for terms drawn from the injection payload itself must
    still just return search results, never trigger any side effect."""
    hits = await search_service.search_notes(
        query="ignore all previous instructions", mode="hybrid", limit=5
    )
    # No exception, no side effect — just a normal (possibly empty-ish)
    # ranked result list.
    assert isinstance(hits, list)
