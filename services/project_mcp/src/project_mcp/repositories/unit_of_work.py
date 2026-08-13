"""The one module in this service that imports `devbrain_common.db`.

Mirrors `services/knowledge_mcp/src/knowledge_mcp/repositories/unit_of_work.py`
— re-exports `session_scope` as `unit_of_work()` so `services/` never imports
`devbrain_common.db` itself. A service's public entry point opens one
`unit_of_work()` and threads the resulting session through however many
repository calls compose that one logical operation (e.g. a status update +
its audit-log row, atomically). Tests monkeypatch this module's
`unit_of_work` to route through the rolled-back-at-teardown `db_session`
fixture instead of opening a real committed transaction.
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
