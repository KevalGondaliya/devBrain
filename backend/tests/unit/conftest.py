"""Puts `tests/unit/` itself on `sys.path` so test modules can `from
_llm_fakes import ...` as a plain bare-name import — same rationale as
every other service's `tests/unit/conftest.py` (avoids a `tests`
package-name collision with `scripts/tests` when this suite runs as part
of a combined monorepo-wide pytest session; see
`services/knowledge_mcp/tests/unit/conftest.py` for the full writeup).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
