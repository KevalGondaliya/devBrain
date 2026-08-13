"""Test fixtures for `devbrain_backend.api` — real `db_test` round-trips.

Unlike a single service's own integration tests, a `TestClient` request
opens its own `devbrain_common.db.session_scope()` (or a service's
`unit_of_work()`, itself a thin wrapper around the same function)
independently per call — there is no single already-open transaction to
share across HTTP calls the way `db_session`'s savepoint-rollback fixture
assumes elsewhere in this repo. So this conftest takes the simpler path:
point `DATABASE_URL` at `db_test` for the whole test session and let
requests commit for real, seeding+truncating the same `--size small
--seed 42` dataset every other phase's integration suite uses, and
additionally truncating `audit_logs`/`approvals` (seed data never touches
those, but this suite's own requests do) before and after the session.

Start the test DB before running this suite:
    docker compose --profile test up -d db_test
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import delete

_REPO_ROOT = Path(__file__).resolve().parents[3]

# --- Reuse packages/common/tests/conftest.py's fixtures by file path, same
# pattern every other phase's integration conftest already uses. ---
_COMMON_CONFTEST = _REPO_ROOT / "packages" / "common" / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location(
    "_devbrain_common_test_fixtures_api", _COMMON_CONFTEST
)
assert _spec is not None and _spec.loader is not None
_common_fixtures = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _common_fixtures
_spec.loader.exec_module(_common_fixtures)

apply_migrations = _common_fixtures.apply_migrations
TEST_DATABASE_URL: str = _common_fixtures.TEST_DATABASE_URL

# --- Make scripts/generate_all.py importable, same as every other phase. ---
_scripts_dir = str(_REPO_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import generate_all  # noqa: E402 - must follow the sys.path insert above

# Set *before* any test/fixture body runs (module-level, at collection-time
# import) so `devbrain_common.config.get_settings()`'s first call anywhere
# in this session already sees `db_test` + these fixed test tokens, never
# the dev DB / `.env`'s tokens. Other suites' own auth tests monkeypatch
# `get_settings` directly rather than relying on process env (see
# `packages/common/tests/unit/test_mcp_auth.py`), so this doesn't leak into
# them even in a combined repo-root `pytest` run.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("DEVBRAIN_LLM_MODE", "stub")
ADMIN_TOKEN = "test-admin-token"
USER_TOKEN = "test-user-token"
VIEWER_TOKEN = "test-viewer-token"
os.environ["MCP_API_TOKENS"] = f"{ADMIN_TOKEN}:admin,{USER_TOKEN}:user,{VIEWER_TOKEN}:viewer"

# Imported only after the env vars above are set, so `devbrain_backend.api
# .main`'s module-level `app = create_app()` never has a chance to resolve
# `get_settings()` against anything but the test configuration.
from devbrain_backend.api.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


async def _truncate_governance_tables(database_url: str) -> None:
    """`audit_logs`/`approvals` are never touched by seed generation
    (ORCHESTRATION.md/Phase 2's own truncate semantics exclude them) but
    this suite's own requests write real rows to both — clean up so runs
    don't accumulate stale approvals/audit rows across sessions."""
    from devbrain_common.db import dispose_engine, session_scope
    from devbrain_common.models import Approval, AuditLog

    async with session_scope(database_url) as session:
        await session.execute(delete(AuditLog))
        await session.execute(delete(Approval))
    await dispose_engine()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_small_dataset(apply_migrations: None) -> AsyncIterator[None]:
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001 - test-only access
    await generate_all._run(  # noqa: SLF001 - test-only access to the runner
        size="small", seed=42, truncate=False, database_url=TEST_DATABASE_URL
    )
    await _truncate_governance_tables(TEST_DATABASE_URL)
    yield
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001
    await _truncate_governance_tables(TEST_DATABASE_URL)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
