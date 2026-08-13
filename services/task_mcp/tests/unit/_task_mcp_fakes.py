"""Shared test doubles for unit tests that mock the repository layer.

Named `_task_mcp_fakes` (not the generic `_fakes` Knowledge MCP uses) so
that when every service's `tests/unit/` directory ends up on `sys.path`
together in one combined pytest session, `import _fakes` doesn't resolve
ambiguously to whichever service's conftest ran first.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class FakeSession:
    """Stand-in for `AsyncSession` — repository calls are mocked out in unit
    tests, so this only needs to exist as a plausible-looking placeholder
    object passed through to those mocks; nothing here executes real SQL."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.flushed = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    async def flush(self) -> None:
        self.flushed = True

    async def refresh(self, obj: Any, attribute_names: list[str] | None = None) -> None:
        return None


@asynccontextmanager
async def fake_unit_of_work(session: FakeSession | None = None) -> AsyncIterator[FakeSession]:
    yield session if session is not None else FakeSession()
