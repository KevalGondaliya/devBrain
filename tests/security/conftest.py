"""Fixtures for `tests/security`.

Most of this suite exercises real MCP servers' `create_server()` +
`call_tool()` dispatch directly (schema validation + auth are enforced
before the service/DB is ever touched, so most tests here need no
database). The HTTP-boundary tests use the `client`/`ADMIN_TOKEN`/
`USER_TOKEN`/`VIEWER_TOKEN`/`seed_small_dataset` fixtures defined once in
`tests/conftest.py` (the parent directory) and inherited here by ordinary
pytest fixture resolution — see that file's own module docstring for why
this suite does not load its own independent copy.

Start the test DB before running this suite:
    docker compose --profile test up -d db_test
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Note: test files in this directory do NOT `from conftest import
# ADMIN_TOKEN, ...` -- a bare `import conftest` is resolved process-wide
# (pytest's own conftest-plugin loading can register these under the plain
# name "conftest" in `sys.modules`, first-loaded-wins), so whichever
# directory's conftest.py happened to load first would silently satisfy
# every other directory's `import conftest` too. Token literals are
# duplicated directly in each test file instead -- see
# `test_authorization_boundaries.py`'s own comment.


@pytest.fixture(autouse=True)
def _reset_stdio_settings_cache() -> Iterator[None]:
    """Each service's `get_<x>_mcp_settings()` is `@lru_cache`d; a test
    that `monkeypatch.setenv`s a `*_MCP_STDIO_ROLE` var *before* that
    service's settings are ever constructed for the first time in this
    process would otherwise poison the cached default permanently for
    every later test in the same combined `pytest` session (`tests/` runs
    before `packages`/`services` in the QA-loop command). Clearing before
    and after removes this suite as a source of that poisoning regardless
    of collection order. (The process-wide rate limiter gets the same
    before/after treatment via `tests/conftest.py`'s `_reset_rate_limiter`,
    inherited here automatically.)
    """
    from knowledge_mcp.config import get_knowledge_mcp_settings
    from project_mcp.config import get_project_mcp_settings
    from task_mcp.config import get_task_mcp_settings

    def _reset() -> None:
        get_task_mcp_settings.cache_clear()
        get_project_mcp_settings.cache_clear()
        get_knowledge_mcp_settings.cache_clear()

    _reset()
    yield
    _reset()


@pytest.fixture
def patched_uow(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> AsyncSession:
    """Route knowledge_mcp/task_mcp/project_mcp's session-opening seam
    through the rolled-back-at-teardown `db_session` (inherited from
    `tests/conftest.py`) for one test."""
    from knowledge_mcp.repositories import unit_of_work as knowledge_uow_module
    from project_mcp.repositories import unit_of_work as project_uow_module
    from task_mcp.repositories import unit_of_work as task_uow_module

    @asynccontextmanager
    async def _fake_unit_of_work(database_url: str | None = None) -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(knowledge_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(task_uow_module, "unit_of_work", _fake_unit_of_work)
    monkeypatch.setattr(project_uow_module, "unit_of_work", _fake_unit_of_work)
    return db_session
