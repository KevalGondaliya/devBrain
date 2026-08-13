"""The one module in this service that imports `devbrain_common.db`.

`devbrain_common/db.py`'s docstring says only repository/adapter code
should import `session_scope`/hold an `AsyncSession` directly. This module
is that repository/adapter seam: it re-exports `session_scope` as
`unit_of_work()` so `services/` never imports `devbrain_common.db` itself —
they import this instead, keeping the "who's allowed to open a DB
connection" surface to exactly one file in this package.

A service's public entry point opens one `unit_of_work()` and threads the
resulting session through however many repository calls compose that one
logical operation (e.g. `notes.create` = insert note + upsert tags + insert
links + insert embedding + write the audit log, all atomically). Tests
override this via `tests/conftest.py`'s `use_db_session_for_uow` fixture to
run against the shared `db_session` fixture (auto-rolled-back savepoint)
instead of a real committed transaction.
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
