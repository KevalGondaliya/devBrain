"""Puts `tests/unit/` itself on `sys.path` so test modules can `from _fakes
import ...` as a plain bare-name import.

Deliberately NOT `from tests.unit._fakes import ...` (a dotted absolute
import): `tests/integration/conftest.py` puts `scripts/` on `sys.path` to
reuse `generate_all.py`, and `scripts/tests/__init__.py` is a *real*
package also named `tests` (Phase 2's convention) — since a regular
`__init__.py`-based package always wins package-name resolution over a
namespace package once found anywhere on `sys.path` (PEP 420), `import
tests` would non-deterministically resolve to `scripts/tests` instead of
this directory whenever both conftest files load in the same pytest
session. A bare `_fakes` import sidesteps the whole `tests` name entirely.
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
    share bucket state via that singleton."""
    reset_rate_limiter()
