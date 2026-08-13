"""Shared pytest fixtures for `packages/common` (and, by import, every later
phase's test suite that needs a real Postgres session).

- `apply_migrations` (session-scoped, autouse): points Alembic at the
  `db_test` service (see root `docker-compose.yml`, profile `test`) and
  runs migrations to `head` once per test session.
- `db_session`: yields an `AsyncSession` wrapped in an outer transaction
  that is rolled back after the test, so tests never leave data behind for
  each other regardless of whether the code under test calls
  `session.commit()` (SQLAlchemy's "join an existing transaction via
  savepoint" pattern).

Start the test DB before running these tests:
    docker compose --profile test up -d db_test
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "postgresql+asyncpg://devbrain_test:devbrain_test@localhost:55432/devbrain_test"

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    """Run Alembic migrations against `db_test` once per test session.

    Sets `DATABASE_URL` for the duration of the process so `alembic/env.py`
    (which prefers `DATABASE_URL` over `Settings().database_url`) targets
    the test database rather than the dev one.
    """
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    cfg = Config(str(_PACKAGE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PACKAGE_ROOT / "alembic"))
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """A per-test `AsyncSession` rolled back after the test completes.

    Uses the "external transaction" pattern: open a connection, begin a
    transaction on it, bind the session to that connection with
    `join_transaction_mode="create_savepoint"` so `session.commit()` calls
    inside the code under test only commit a savepoint, not the outer
    transaction — the whole thing rolls back at fixture teardown.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            outer_tx = await conn.begin()
            session_factory = async_sessionmaker(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            async with session_factory() as session:
                yield session
            await outer_tx.rollback()
    finally:
        await engine.dispose()
