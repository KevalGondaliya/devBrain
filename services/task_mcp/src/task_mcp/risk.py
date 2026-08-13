"""Risk-tier classification for this service's tools (DevBrain_vision.md §10).

- **Low** (read-only, auto-executed): `list_tasks`, `search_tasks`, `get_task`.
- **Medium** (approval-gated as of Phase 6 — see `devbrain_common.approvals`):
  `create_task`, `update_task`, `complete_task`.
- **High**: none in this service's tool surface — no delete/bulk tool is
  part of Task MCP's spec (DevBrain_vision.md §11.3), so none is invented
  here.

The `RiskTier` enum and the `risk_tier_for`/`approval_required` lookup
boilerplate are shared (`devbrain_common.risk.make_risk_lookup`) — this
module's own job is just the tool-name -> tier data, which is genuinely
service-specific.
"""

from __future__ import annotations

from devbrain_common.risk import RiskTier, make_risk_lookup

_TOOL_RISK_TIERS: dict[str, RiskTier] = {
    "list_tasks": RiskTier.LOW,
    "search_tasks": RiskTier.LOW,
    "get_task": RiskTier.LOW,
    "create_task": RiskTier.MEDIUM,
    "update_task": RiskTier.MEDIUM,
    "complete_task": RiskTier.MEDIUM,
}

risk_tier_for, approval_required = make_risk_lookup(_TOOL_RISK_TIERS)

__all__ = ["RiskTier", "approval_required", "risk_tier_for"]
