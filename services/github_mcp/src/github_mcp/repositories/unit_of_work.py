"""The one module in this service that imports `devbrain_common.db`.

Mirrors `services/task_mcp/src/task_mcp/repositories/unit_of_work.py` —
re-exports `session_scope` as `unit_of_work()` so `services/`/`adapters/`
never import `devbrain_common.db` themselves. A service's public entry
point opens one `unit_of_work()`, builds the adapter for that session (see
`services/github_service.py::get_adapter`), and threads the resulting
session through however many adapter/repository calls compose that one
logical operation. Tests monkeypatch this module's `unit_of_work` to route
through the rolled-back-at-teardown `db_session` fixture instead of opening
a real committed transaction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from devbrain_common.db import session_scope
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def unit_of_work(database_url: str | None = None) -> AsyncIterator[AsyncSession]:
    """Open a transactional `AsyncSession` for one service-level operation."""
    async with session_scope(database_url) as session:
        yield session
