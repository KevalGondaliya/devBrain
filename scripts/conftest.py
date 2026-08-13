"""Makes `scripts/` importable as a plain (non-package) directory for pytest.

`scripts/generate_all.py` is run directly (`python scripts/generate_all.py`),
not via `python -m`, so `generators/` and `embeddings.py` are deliberately
*not* nested under a `scripts` package — see that file's own sys.path
comment. Pytest, however, discovers `scripts/tests/**` from the repo root,
so this conftest exists purely so pytest's collection prepends `scripts/`
(this file's directory) onto `sys.path`, letting test modules do
`import generators.xyz` / `import embeddings` / `import generate_all` the
same way `generate_all.py` imports its own siblings.

`scripts/tests/` (unlike `scripts/` itself) *is* a real package (has
`__init__.py`) so pytest collects its modules as `tests.unit.test_*` /
`tests.integration.test_*` off this same `scripts/` sys.path root, and they
can use ordinary relative imports (`from ._helpers import ...`) between
themselves — this is also why `MYPYPATH` for `mypy` only needs
`scripts` added, not `scripts/tests/unit` too (see PROGRESS_REPORT.md).
"""

from __future__ import annotations
