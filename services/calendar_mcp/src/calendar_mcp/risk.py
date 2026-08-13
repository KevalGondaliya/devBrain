"""Risk-tier classification for this service's tools (DevBrain_vision.md §10).

- **Low** (read, auto-executed): `get_today_events`, `get_week_events`,
  `find_event`.
- **Medium** (approval-gated as of Phase 6 — see `devbrain_common.approvals`):
  `create_event` — this service's one write tool.
- **High**: none in this service's tool surface — no delete/bulk tool is
  part of Calendar MCP's spec (DevBrain_vision.md §11.5), so none is
  invented here.

The `RiskTier` enum and the `risk_tier_for`/`approval_required` lookup
boilerplate are shared (`devbrain_common.risk.make_risk_lookup`) — this
module's own job is just the tool-name -> tier data, which is genuinely
service-specific.
"""

from __future__ import annotations

from devbrain_common.risk import RiskTier, make_risk_lookup

_TOOL_RISK_TIERS: dict[str, RiskTier] = {
    "get_today_events": RiskTier.LOW,
    "get_week_events": RiskTier.LOW,
    "find_event": RiskTier.LOW,
    "create_event": RiskTier.MEDIUM,
}

risk_tier_for, approval_required = make_risk_lookup(_TOOL_RISK_TIERS)

__all__ = ["RiskTier", "approval_required", "risk_tier_for"]
