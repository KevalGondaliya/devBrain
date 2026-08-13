"""Integration test fixtures for the Phase 7 agent orchestrators.

Reuses `apply_migrations`/`db_session`/`TEST_DATABASE_URL` from
`packages/common/tests/conftest.py` (loaded by file path — see
`services/knowledge_mcp/tests/integration/conftest.py` for the full
rationale) and Phase 2's `scripts/generate_all.py` seeding, exactly like
every prior phase's integration suite.

Unlike a single service's integration conftest, the orchestrators under
test here call into *two* services' unit-of-work seams
(`knowledge_mcp.repositories.unit_of_work` for notes,
`task_mcp.repositories.unit_of_work` for tasks) plus
`devbrain_backend.agents.safe_write`'s own direct
`devbrain_common.db.session_scope` call — so this conftest patches all
three to the same rolled-back-at-teardown `db_session`, so a write made
through one seam is visible to a read made through another within one test
(they're literally the same open transaction).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

_REPO_ROOT = Path(__file__).resolve().parents[3]

# --- Reuse packages/common/tests/conftest.py's fixtures by file path ---
_COMMON_CONFTEST = _REPO_ROOT / "packages" / "common" / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("_devbrain_common_test_fixtures", _COMMON_CONFTEST)
assert _spec is not None and _spec.loader is not None
_common_fixtures = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _common_fixtures
_spec.loader.exec_module(_common_fixtures)

apply_migrations = _common_fixtures.apply_migrations
db_session = _common_fixtures.db_session
TEST_DATABASE_URL: str = _common_fixtures.TEST_DATABASE_URL

# --- Make scripts/generate_all.py importable, same as scripts/conftest.py does ---
_scripts_dir = str(_REPO_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import generate_all  # noqa: E402 - must follow the sys.path insert above


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_small_dataset(apply_migrations: None) -> AsyncIterator[None]:
    """Seed `db_test` with `--size small --seed 42` once for this test
    session; truncate before and after (same seed as every other phase's
    integration suite — includes the prompt-injection fixture note)."""
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001 - test-only access
    await generate_all._run(  # noqa: SLF001 - test-only access to the runner
        size="small", seed=42, truncate=False, database_url=TEST_DATABASE_URL
    )
    yield
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001


@pytest.fixture
def patched_uow(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> AsyncSession:
    """Route `knowledge_mcp`, `task_mcp`, and
    `devbrain_backend.agents.safe_write`'s own session-opening seams all
    through the same rolled-back-at-teardown `db_session` for this one
    test, so orchestrators that touch more than one service's tables see
    one consistent, atomic-looking transaction.
    """
    from devbrain_backend.agents import safe_write as safe_write_module
    from knowledge_mcp.repositories import unit_of_work as knowledge_uow_module
    from task_mcp.repositories import unit_of_work as task_uow_module

    @asynccontextmanager
    async def _fake_unit_of_work(database_url: str | None = None) -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(knowledge_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(task_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(safe_write_module, "session_scope", _fake_unit_of_work)
    return db_session
