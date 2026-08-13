"""Search ranking/merge logic — pure functions, no DB."""

from __future__ import annotations

import uuid

from knowledge_mcp.services.search_service import (
    HYBRID_KEYWORD_WEIGHT,
    HYBRID_SEMANTIC_WEIGHT,
    KEYWORD_BODY_SCORE,
    KEYWORD_TITLE_SCORE,
    keyword_score,
    merge_hybrid_results,
    semantic_similarity,
)


def test_keyword_score_title_beats_body() -> None:
    assert keyword_score(title_matched=True) == KEYWORD_TITLE_SCORE
    assert keyword_score(title_matched=False) == KEYWORD_BODY_SCORE
    assert keyword_score(title_matched=True) > keyword_score(title_matched=False)


class TestSemanticSimilarity:
    def test_identical_vector_is_max_similarity(self) -> None:
        assert semantic_similarity(0.0) == 1.0

    def test_opposite_vector_is_min_similarity(self) -> None:
        assert semantic_similarity(2.0) == 0.0

    def test_orthogonal_is_midpoint(self) -> None:
        assert semantic_similarity(1.0) == 0.5

    def test_clamped_within_bounds(self) -> None:
        assert semantic_similarity(-0.5) == 1.0
        assert semantic_similarity(3.0) == 0.0


class TestMergeHybridResults:
    def test_note_in_both_sets_gets_combined_score_and_both_label(self) -> None:
        note_id = uuid.uuid4()
        merged = merge_hybrid_results({note_id: 1.0}, {note_id: 1.0}, limit=10)
        assert len(merged) == 1
        result_id, score, via = merged[0]
        assert result_id == note_id
        assert score == HYBRID_KEYWORD_WEIGHT * 1.0 + HYBRID_SEMANTIC_WEIGHT * 1.0
        assert via == "both"

    def test_keyword_only_hit_labeled_keyword(self) -> None:
        note_id = uuid.uuid4()
        merged = merge_hybrid_results({note_id: 1.0}, {}, limit=10)
        assert merged == [(note_id, HYBRID_KEYWORD_WEIGHT * 1.0, "keyword")]

    def test_semantic_only_hit_labeled_semantic(self) -> None:
        note_id = uuid.uuid4()
        merged = merge_hybrid_results({}, {note_id: 0.8}, limit=10)
        assert merged == [(note_id, HYBRID_SEMANTIC_WEIGHT * 0.8, "semantic")]

    def test_sorted_descending_by_combined_score(self) -> None:
        low, mid, high = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        merged = merge_hybrid_results(
            {low: 0.1, mid: 0.5, high: 1.0}, {low: 0.1, mid: 0.5, high: 1.0}, limit=10
        )
        assert [m[0] for m in merged] == [high, mid, low]

    def test_respects_limit(self) -> None:
        ids = [uuid.uuid4() for _ in range(5)]
        keyword_hits = {note_id: 1.0 - i * 0.1 for i, note_id in enumerate(ids)}
        merged = merge_hybrid_results(keyword_hits, {}, limit=2)
        assert len(merged) == 2

    def test_empty_inputs_yield_empty_result(self) -> None:
        assert merge_hybrid_results({}, {}, limit=10) == []
