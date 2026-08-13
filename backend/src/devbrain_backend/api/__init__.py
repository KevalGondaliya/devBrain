"""Phase 8 — FastAPI HTTP surface over DevBrain's five MCP services'
`services/*.py` layers and the Phase 7 agent orchestrators.

Nothing here talks to the database directly except the two places that
have no existing service-level primitive to reuse (`activity.py`'s
`audit_logs` listing, `approvals.py`'s thin wrapper over
`devbrain_common.approvals`) — everything else is a direct call into
already-tested code from Phases 3-7. See `main.py` for the app factory and
`ORCHESTRATION.md`'s Phase 8 entry / `PROGRESS_REPORT.md`'s Phase 8 section
for the full design writeup.
"""

from __future__ import annotations
