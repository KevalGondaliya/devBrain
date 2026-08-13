"""Fixtures for `tests/e2e` — real HTTP requests (via `fastapi.testclient
.TestClient`) against the real FastAPI backend, a real seeded `db_test`, no
mocking anywhere in the stack.

The `client`/`seed_small_dataset` fixtures this suite needs are defined
once in `tests/conftest.py` (the parent directory) and inherited here by
ordinary pytest fixture resolution — see that file's own module docstring
for why this suite does not load its own independent copy (two
independently-loaded copies of the same session-scoped truncate+reseed
fixture raced each other for the same physical `db_test` in an earlier
revision of this suite).

This directory has nothing of its own to add — the file exists so pytest
recognizes `tests/e2e/` as a collectible package boundary alongside its
siblings; all real fixture logic lives in `tests/conftest.py`.

Start the test DB before running this suite:
    docker compose --profile test up -d db_test
"""

from __future__ import annotations
