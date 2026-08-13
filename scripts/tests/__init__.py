"""Phase 2 test suite for `scripts/generate_all.py` and `scripts/generators/`.

A real package (has `__init__.py`, unlike `scripts/generators/`'s sibling
`scripts/` directory) so pytest imports test modules as `tests.unit.test_*`
/ `tests.integration.test_*` and `mypy` resolves them consistently — see
`scripts/conftest.py` for how `scripts/` itself lands on `sys.path`.
"""

from __future__ import annotations
