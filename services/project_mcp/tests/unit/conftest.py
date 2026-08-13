"""Puts `tests/unit/` itself on `sys.path` so test modules can `from
_project_mcp_fakes import ...` as a plain bare-name import. See
`services/knowledge_mcp/tests/unit/conftest.py` for the rationale on why
this uses bare-name imports at all (avoids a `tests` package-name collision
with `scripts/tests` in a combined monorepo-wide pytest session).

The fakes module is named `_project_mcp_fakes` (not the generic `_fakes`
Knowledge MCP uses) so that when every service's `tests/unit/` directory
ends up on `sys.path` together in one combined pytest session, `import
_fakes` doesn't resolve ambiguously to whichever service's conftest ran
first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from devbrain_common.ratelimit import reset_rate_limiter

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Phase 6: `require_min_role` now checks the process-wide rate
    limiter singleton. Reset it before every test so unrelated tests never
    share bucket state via that singleton (see PROGRESS_REPORT.md Phase 6
    "Decisions made")."""
    reset_rate_limiter()
