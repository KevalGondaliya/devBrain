"""Shared fixtures for `tests/e2e` and `tests/security` — both need a real,
seeded `db_test` plus a real FastAPI `TestClient` against the real backend
app. Defined **once**, here, at the `tests/` root, so pytest's native
fixture inheritance gives every consumer the exact same fixture instances.

(`tests/eval` deliberately keeps its own independent, non-HTTP seeding in
`tests/eval/conftest.py` — predates this file, never touches the HTTP
surface, and shadows the `seed_small_dataset` fixture defined below for
everything under `tests/eval/`, per ordinary pytest fixture-override rules,
so the two don't double-seed each other.)

Earlier revisions of this suite had `tests/e2e/conftest.py` and
`tests/security/conftest.py` each independently `importlib`-load
`backend/tests/api/conftest.py` by file path under their own module name —
two *different* Python module objects executing the same source, which
pytest's fixture manager registers as two independent session-scoped
`seed_small_dataset` fixtures. Each would truncate-then-reseed the same
physical `db_test` on first use, and because pytest only guarantees strict
ordering *within* one fixture's own setup/teardown (not across two
independently-identified fixtures that happen to share source code), this
occasionally raced: one copy's reseed insert landing while another copy's
leftover rows (or a still-in-flight truncate) were present, producing a
`UniqueViolationError` on a deterministic seed-derived slug. Defining the
fixture exactly once here, inherited rather than re-loaded, removes the
second identity entirely — there is only one `seed_small_dataset` fixture
in play for `tests/e2e` + `tests/security` combined.

Start the test DB before running any suite under `tests/`:
    docker compose --profile test up -d db_test
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete

_REPO_ROOT = Path(__file__).resolve().parent.parent

# --- packages/common's apply_migrations / db_session / TEST_DATABASE_URL,
# loaded by file path (same pattern every integration conftest in this
# repo uses, since packages/common/tests isn't an importable package from
# here). ---
_COMMON_CONFTEST = _REPO_ROOT / "packages" / "common" / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location(
    "_devbrain_common_test_fixtures_tests_root", _COMMON_CONFTEST
)
assert _spec is not None and _spec.loader is not None
_common_fixtures = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _common_fixtures
_spec.loader.exec_module(_common_fixtures)

apply_migrations = _common_fixtures.apply_migrations
db_session = _common_fixtures.db_session
TEST_DATABASE_URL: str = _common_fixtures.TEST_DATABASE_URL

# --- scripts/generate_all.py, same as every other integration conftest ---
_scripts_dir = str(_REPO_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import generate_all  # noqa: E402 - must follow the sys.path insert above

# --- Fixed test tokens + env, set BEFORE importing the backend app (import
# order matters here -- devbrain_backend.api.main's module-level
# `app = create_app()` must never see the dev DATABASE_URL/MCP_API_TOKENS;
# mirrors backend/tests/api/conftest.py's own sequencing exactly). ---
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("DEVBRAIN_LLM_MODE", "stub")
ADMIN_TOKEN = "test-admin-token"
USER_TOKEN = "test-user-token"
VIEWER_TOKEN = "test-viewer-token"
os.environ["MCP_API_TOKENS"] = f"{ADMIN_TOKEN}:admin,{USER_TOKEN}:user,{VIEWER_TOKEN}:viewer"

from devbrain_backend.api.main import app  # noqa: E402


async def _truncate_governance_tables() -> None:
    """`audit_logs`/`approvals` are never touched by seed generation but
    this suite's own requests write real rows to both -- clean up so runs
    don't accumulate stale rows across sessions (same as
    `backend/tests/api/conftest.py`'s identical helper)."""
    from devbrain_common.db import dispose_engine, session_scope
    from devbrain_common.models import Approval, AuditLog

    async with session_scope(TEST_DATABASE_URL) as session:
        await session.execute(delete(AuditLog))
        await session.execute(delete(Approval))
    await dispose_engine()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_small_dataset(apply_migrations: None) -> AsyncIterator[None]:
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001 - test-only access
    await generate_all._run(  # noqa: SLF001 - test-only access to the runner
        size="small", seed=42, truncate=False, database_url=TEST_DATABASE_URL
    )
    await _truncate_governance_tables()
    yield
    await generate_all._truncate(TEST_DATABASE_URL)  # noqa: SLF001
    await _truncate_governance_tables()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """`devbrain_common.ratelimit.get_rate_limiter()` is one process-wide
    singleton shared by every service and the backend -- real dispatches
    made by `tests/e2e`/`tests/security` consume real tokens from those
    shared buckets. Reset before and after every test in either suite, same
    precedent every service's own `tests/unit/conftest.py` established for
    their own unit suites."""
    from devbrain_common.ratelimit import reset_rate_limiter

    reset_rate_limiter()
    yield
    reset_rate_limiter()
