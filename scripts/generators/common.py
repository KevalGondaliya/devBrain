"""Shared helpers for the Phase 2 dummy-data generators.

Kept dependency-free (stdlib only) so every generator module can import it
without pulling in Faker/SQLAlchemy specifics.
"""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime, timedelta

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, hyphenate, and strip a string down to a URL-safe slug."""
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "note"


def unique_slug(base: str, taken: set[str]) -> str:
    """Slugify `base` and disambiguate against `taken` with a numeric suffix.

    Mutates `taken` by adding the returned slug, so callers can pass the same
    set across many calls to guarantee global uniqueness (mirrors the
    `notes.slug` unique constraint in `devbrain_common.models`).
    """
    base_slug = slugify(base)
    candidate = base_slug
    n = 2
    while candidate in taken:
        candidate = f"{base_slug}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def utcnow() -> datetime:
    return datetime.now(UTC)


def random_datetime_between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """A uniformly random tz-aware datetime in `[start, end]` (or `start` if `end <= start`)."""
    if end <= start:
        return start
    delta = end - start
    offset_seconds = rng.uniform(0, delta.total_seconds())
    return start + timedelta(seconds=offset_seconds)
