"""Hybrid keyword + semantic note search.

Ranking design (documented here since it's the flagship demo feature):
  - keyword score: 1.0 if the query substring appears in the note's title
    (case-insensitive `ILIKE`), else 0.6 if it only appears in the body.
    This is a cheap proxy for relevance, not real BM25 — good enough to
    demo "search actually works" without pulling in a full-text ranking
    dependency.
  - semantic score: cosine *distance* from `repositories.notes_repository
    .search_semantic` (0 = identical, 2 = opposite) is converted to a
    0..1 *similarity* via `1 - distance / 2`.
  - hybrid score: an even 0.5/0.5 blend of the two, defaulting a hit's
    missing side to 0 (e.g. a note that only matched semantically gets
    `0.5 * 0 + 0.5 * similarity`).

`merge_hybrid_results` is a pure function (no DB, no repository) so the
ranking/merge logic is unit-testable on its own — see
`tests/unit/test_search_service.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from devbrain_common.config import get_settings
from devbrain_common.errors import ValidationError
from devbrain_common.models import Note

from knowledge_mcp.repositories import notes_repository as notes_repository
from knowledge_mcp.repositories import unit_of_work as uow
from knowledge_mcp.services import embeddings as embeddings
from knowledge_mcp.services.notes_service import NoteDTO, note_to_dto

SearchMode = Literal["hybrid", "keyword", "semantic"]
_VALID_MODES = ("hybrid", "keyword", "semantic")

KEYWORD_TITLE_SCORE = 1.0
KEYWORD_BODY_SCORE = 0.6
HYBRID_KEYWORD_WEIGHT = 0.5
HYBRID_SEMANTIC_WEIGHT = 0.5


@dataclass(frozen=True)
class SearchHit:
    note: NoteDTO
    score: float
    matched_via: Literal["keyword", "semantic", "both"]


def keyword_score(title_matched: bool) -> float:
    return KEYWORD_TITLE_SCORE if title_matched else KEYWORD_BODY_SCORE


def semantic_similarity(cosine_distance: float) -> float:
    """Cosine distance in `[0, 2]` -> similarity in `[0, 1]` (clamped)."""
    similarity = 1.0 - (cosine_distance / 2.0)
    return max(0.0, min(1.0, similarity))


def merge_hybrid_results(
    keyword_hits: dict[uuid.UUID, float],
    semantic_hits: dict[uuid.UUID, float],
    limit: int,
) -> list[tuple[uuid.UUID, float, Literal["keyword", "semantic", "both"]]]:
    """Blend two `{note_id: score}` maps (both already 0..1) into one ranked
    list. Pure function — no I/O, fully unit-testable.
    """
    all_ids = set(keyword_hits) | set(semantic_hits)
    merged: list[tuple[uuid.UUID, float, Literal["keyword", "semantic", "both"]]] = []
    for note_id in all_ids:
        k = keyword_hits.get(note_id, 0.0)
        s = semantic_hits.get(note_id, 0.0)
        combined = HYBRID_KEYWORD_WEIGHT * k + HYBRID_SEMANTIC_WEIGHT * s
        if note_id in keyword_hits and note_id in semantic_hits:
            via: Literal["keyword", "semantic", "both"] = "both"
        elif note_id in keyword_hits:
            via = "keyword"
        else:
            via = "semantic"
        merged.append((note_id, combined, via))
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged[:limit]


async def search_notes(
    *, query: str, mode: SearchMode = "hybrid", limit: int = 10
) -> list[SearchHit]:
    if not query.strip():
        raise ValidationError("query must not be empty.")
    if mode not in _VALID_MODES:
        raise ValidationError(f"mode must be one of {_VALID_MODES}.")
    if limit < 1 or limit > 100:
        raise ValidationError("limit must be between 1 and 100.")

    model_name = get_settings().embedding_model

    async with uow.unit_of_work() as session:
        notes_by_id: dict[uuid.UUID, Note] = {}
        keyword_hits: dict[uuid.UUID, float] = {}
        semantic_hits: dict[uuid.UUID, float] = {}

        if mode in ("keyword", "hybrid"):
            keyword_rows = await notes_repository.search_keyword(session, query, limit * 2)
            for note, title_matched in keyword_rows:
                notes_by_id[note.id] = note
                keyword_hits[note.id] = keyword_score(title_matched)

        if mode in ("semantic", "hybrid"):
            query_vector = embeddings.encode_text(query, model_name)
            semantic_rows = await notes_repository.search_semantic(session, query_vector, limit * 2)
            for note, distance in semantic_rows:
                notes_by_id[note.id] = note
                semantic_hits[note.id] = semantic_similarity(distance)

        merged: list[tuple[uuid.UUID, float, Literal["keyword", "semantic", "both"]]]
        if mode == "keyword":
            ranked = sorted(keyword_hits.items(), key=lambda kv: kv[1], reverse=True)[:limit]
            merged = [(note_id, score, "keyword") for note_id, score in ranked]
        elif mode == "semantic":
            ranked = sorted(semantic_hits.items(), key=lambda kv: kv[1], reverse=True)[:limit]
            merged = [(note_id, score, "semantic") for note_id, score in ranked]
        else:
            merged = merge_hybrid_results(keyword_hits, semantic_hits, limit)

        return [
            SearchHit(note=note_to_dto(notes_by_id[note_id]), score=score, matched_via=via)
            for note_id, score, via in merged
        ]
