"""Phase 2 dummy-data generators, one module per entity.

Every `generate_*` function in this package is pure (no DB, no network,
no filesystem) and deterministic given the same `Faker` instance and
`random.Random` instance — see `scripts/generate_all.py` for how they're
wired together in DevBrain_vision.md §13's dependency order, and
`scripts/tests/unit/` for tests that exercise them without a database.
"""

from __future__ import annotations
