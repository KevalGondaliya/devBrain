"""Risk-tier classification for this service's tools (DevBrain_vision.md §10).

Added post-Phase-6 to close a gap Phase 8's agent flagged (see
PROGRESS_REPORT.md's Phase 6 addendum): Knowledge MCP shipped in Phase 3
before Phase 6's approval gate existed, and unlike Project/Task/GitHub/
Calendar MCP it was never revisited to wire `enforce_approval` into its
writes. This module (and the corresponding service/tool changes) close
that gap.

- **Low** (read-only, auto-executed): `notes.get`, `notes.search`,
  `tags.list`, `links.get_backlinks`, `links.get_graph`, `search_meetings`,
  `read_meeting`, `search_decisions`, `get_decision`.
- **Medium** (approval-gated — see `devbrain_common.approvals`):
  `notes.create`, `notes.update`, `tags.rename`. Same shape as every other
  service's medium tier: `Role.ADMIN` callers bypass (audited), `Role.USER`
  callers need a valid `approval_id`.
- **High** (approval-gated *and* admin-only, no either/or): `notes.delete`.
  `DevBrain_vision.md` §10 lists high risk as "strong approval **or**
  admin-only" as two illustrative options, but §12's own worked example
  matrix resolves that ambiguity for a destructive tool exactly like this
  one — `delete_task`/`bulk_update` are both listed `Admin: Yes` **and**
  `Approval: Yes` simultaneously, i.e. admin status alone does not waive
  the approval requirement for a high-risk write. No service before this
  one had a high-risk tool to copy the pattern from (every other service's
  own `risk.py` says so explicitly), so `notes.delete` is the first, and
  this module's `_enforce_high_risk_approval` in `notes_service.py`
  deliberately does *not* reuse `devbrain_common.approvals.enforce_approval`
  (which bypasses entirely for `Role.ADMIN`) — it requires `Role.ADMIN`
  *and* a valid, matching, unconsumed `approval_id`, unconditionally.

The `RiskTier` enum and the `risk_tier_for`/`approval_required` lookup
boilerplate are shared (`devbrain_common.risk.make_risk_lookup`) — this
module's own job is just the tool-name -> tier data, which is genuinely
service-specific. `approval_required` is `True` for both `MEDIUM` and
`HIGH` (shared module's documented behavior), which is the correct
"needs a human sign-off" signal for `tools/notes_tools.py`'s
`approval_recommended` response stamping even though `notes.delete`'s
actual gate is stricter than "recommended".
"""

from __future__ import annotations

from devbrain_common.risk import RiskTier, make_risk_lookup

_TOOL_RISK_TIERS: dict[str, RiskTier] = {
    "notes.get": RiskTier.LOW,
    "notes.search": RiskTier.LOW,
    "tags.list": RiskTier.LOW,
    "links.get_backlinks": RiskTier.LOW,
    "links.get_graph": RiskTier.LOW,
    "search_meetings": RiskTier.LOW,
    "read_meeting": RiskTier.LOW,
    "search_decisions": RiskTier.LOW,
    "get_decision": RiskTier.LOW,
    "notes.create": RiskTier.MEDIUM,
    "notes.update": RiskTier.MEDIUM,
    "tags.rename": RiskTier.MEDIUM,
    "notes.delete": RiskTier.HIGH,
}

risk_tier_for, approval_required = make_risk_lookup(_TOOL_RISK_TIERS)

__all__ = ["RiskTier", "approval_required", "risk_tier_for"]
