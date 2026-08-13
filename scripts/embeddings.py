"""Compute sentence-transformers embeddings for generated notes.

Kept as its own module (rather than folded into `generators/notes.py`) so
the pure-logic generators stay free of the `sentence-transformers`/`torch`
dependency chain — `scripts/tests/unit/` imports the generators directly and
should run fast with no model download. Only `generate_all.py` (and this
module) needs the heavy embeddings stack.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from devbrain_common.models import EMBEDDING_DIM, Embedding, Note

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_MODEL_CACHE: dict[str, SentenceTransformer] = {}


def _get_model(model_name: str) -> SentenceTransformer:
    if model_name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer

        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


def compute_note_embeddings(
    notes: list[Note], model_name: str, batch_size: int = 64
) -> list[Embedding]:
    """Batch-encode `title + content` for every note; one `Embedding` row per note.

    Batching (rather than encoding one note at a time) is what makes this
    reasonable for the "default"/"large" dataset sizes on CPU.
    """
    if not notes:
        return []
    model = _get_model(model_name)
    texts = [f"{n.title}\n\n{n.content}" for n in notes]
    vectors: Any = model.encode(
        texts, batch_size=batch_size, show_progress_bar=False, convert_to_numpy=True
    )
    embeddings: list[Embedding] = []
    for note, vector in zip(notes, vectors, strict=True):
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"model {model_name!r} produced a {len(vector)}-dim vector, "
                f"expected {EMBEDDING_DIM} to match the `embeddings.vector` schema column"
            )
        embeddings.append(
            Embedding(
                id=uuid.uuid4(),
                note_id=note.id,
                vector=vector.tolist(),
                model_name=model_name,
            )
        )
    return embeddings
