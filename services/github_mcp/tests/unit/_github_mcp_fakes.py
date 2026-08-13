"""Shared test doubles for unit tests.

Named `_github_mcp_fakes` (not the generic `_fakes` Knowledge MCP uses) so
that when every service's `tests/unit/` directory ends up on `sys.path`
together in one combined pytest session, `import _fakes` doesn't resolve
ambiguously to whichever service's conftest ran first — same convention as
`services/task_mcp/tests/unit/_task_mcp_fakes.py`.
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


@asynccontextmanager
async def fake_unit_of_work(database_url: str | None = None) -> AsyncIterator[FakeSession]:
    yield FakeSession()
