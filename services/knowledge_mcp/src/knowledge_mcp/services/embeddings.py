"""Sentence-transformers wrapper: same model family as Phase 2's seeder.

Uses `devbrain_common.config.Settings.embedding_model` (`EMBEDDING_MODEL`
env var, default `all-MiniLM-L6-v2` — same as `scripts/embeddings.py`'s
default) so query embeddings and the embeddings `scripts/generate_all.py`
stored at seed time live in the same vector space and are directly
comparable via cosine distance.

Mirrors `scripts/embeddings.py`'s lazy-import-and-cache-by-name pattern for
the same reason that module documents: keep `sentence-transformers`/`torch`
out of the import path for anything that doesn't need them (here: the
`tools`/`repositories` layers, and every unit test that mocks this module
out rather than importing it for real).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_MODEL_CACHE: dict[str, SentenceTransformer] = {}


def _get_model(model_name: str) -> SentenceTransformer:
    if model_name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer

        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


def note_embedding_text(title: str, content: str) -> str:
    """The exact text encoded per note — must match `scripts/embeddings.py`'s
    `f"{title}\\n\\n{content}"` convention so stored and query vectors are
    comparable."""
    return f"{title}\n\n{content}"


def encode_texts(texts: list[str], model_name: str, batch_size: int = 32) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model(model_name)
    vectors: Any = model.encode(
        texts, batch_size=batch_size, show_progress_bar=False, convert_to_numpy=True
    )
    return [vector.tolist() for vector in vectors]


def encode_text(text: str, model_name: str) -> list[float]:
    return encode_texts([text], model_name)[0]
