"""Fixtures for `tests/eval` — real `db_test` round-trips against the
actual orchestrators/services, `DEVBRAIN_LLM_MODE=stub` (no live API key
needed, see `packages/common/src/devbrain_common/llm.py`).

Reuses `apply_migrations`/`db_session`/`TEST_DATABASE_URL` from
`packages/common/tests/conftest.py` (loaded by file path, same pattern
every other phase's integration conftest uses) and Phase 2's
`scripts/generate_all.py` seeding.

Scenario runners touch up to *five* services' unit-of-work seams at once
(a daily briefing alone reads calendar, task, project, knowledge, and
GitHub data) plus `devbrain_backend.agents.safe_write`'s own direct
`devbrain_common.db.session_scope` call — so `patched_uow` routes all of
them through one rolled-back-at-teardown `db_session`, exactly like
`backend/tests/integration/conftest.py`'s fixture of the same name, just
extended from two services to all five.

Start the test DB before running this suite:
    docker compose --profile test up -d db_test
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

_REPO_ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("DEVBRAIN_LLM_MODE", "stub")

# --- Reuse packages/common/tests/conftest.py's fixtures by file path ---
_COMMON_CONFTEST = _REPO_ROOT / "packages" / "common" / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location(
    "_devbrain_common_test_fixtures_eval", _COMMON_CONFTEST
)
assert _spec is not None and _spec.loader is not None
_common_fixtures = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _common_fixtures
_spec.loader.exec_module(_common_fixtures)

apply_migrations = _common_fixtures.apply_migrations
db_session = _common_fixtures.db_session
TEST_DATABASE_URL: str = _common_fixtures.TEST_DATABASE_URL

# --- Make scripts/generate_all.py importable, same as every other phase ---
_scripts_dir = str(_REPO_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import generate_all  # noqa: E402 - must follow the sys.path insert above


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_small_dataset(apply_migrations: None) -> AsyncIterator[None]:
    """Seed `db_test` with `--size small --seed 42` once for this test
    session (includes the prompt-injection fixture note the security
    scenarios need); truncate before and after."""
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001 - test-only access
    await generate_all._run(  # noqa: SLF001 - test-only access to the runner
        size="small", seed=42, truncate=False, database_url=TEST_DATABASE_URL
    )
    yield
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001


@pytest.fixture
def patched_uow(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> AsyncSession:
    """Route every service's session-opening seam through the same
    rolled-back-at-teardown `db_session` for this one test."""
    from calendar_mcp.repositories import unit_of_work as calendar_uow_module
    from devbrain_backend.agents import safe_write as safe_write_module
    from github_mcp.repositories import unit_of_work as github_uow_module
    from knowledge_mcp.repositories import unit_of_work as knowledge_uow_module
    from project_mcp.repositories import unit_of_work as project_uow_module
    from task_mcp.repositories import unit_of_work as task_uow_module

    @asynccontextmanager
    async def _fake_unit_of_work(database_url: str | None = None) -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(knowledge_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(project_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(task_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(github_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(calendar_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(safe_write_module, "session_scope", _fake_unit_of_work)
    return db_session
