"""Applies Phase 1's Alembic migrations to `db_test` once per test session.

Mirrors `packages/common/tests/conftest.py`'s `apply_migrations` fixture —
duplicated rather than imported because `packages/common/tests` isn't an
importable package from here, and this is a two-line fixture.

Start the test DB before running these tests:
    docker compose --profile test up -d db_test
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

TEST_DATABASE_URL = "postgresql+asyncpg://devbrain_test:devbrain_test@localhost:55432/devbrain_test"

_COMMON_PKG_ROOT = Path(__file__).resolve().parents[3] / "packages" / "common"


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    cfg = Config(str(_COMMON_PKG_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_COMMON_PKG_ROOT / "alembic"))
    command.upgrade(cfg, "head")
