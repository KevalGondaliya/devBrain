"""Risk-tier classification for this service's tools (DevBrain_vision.md §10).

- **Low** (read-only, auto-executed): `list_projects`, `search_projects`,
  `get_project`, `get_project_status`.
- **Medium** (approval-gated as of Phase 6 — see
  `devbrain_common.approvals`): `update_project_status`.
- **High**: none in this service's tool surface — no delete/bulk tool is
  part of Project MCP's spec (DevBrain_vision.md §11.2), so none is invented
  here.

The `RiskTier` enum and the `risk_tier_for`/`approval_required` lookup
boilerplate are shared (`devbrain_common.risk.make_risk_lookup`) — this
module's own job is just the tool-name -> tier data, which is genuinely
service-specific. `tools/projects_tools.py` attaches `approval_required`'s
result as informational metadata (`approval_recommended`) on medium-risk
tool responses, and `services/projects_service.py`'s
`update_project_status` calls `devbrain_common.approvals.enforce_approval`
to actually gate the call for non-admin callers.
"""

from __future__ import annotations

from devbrain_common.risk import RiskTier, make_risk_lookup

_TOOL_RISK_TIERS: dict[str, RiskTier] = {
    "list_projects": RiskTier.LOW,
    "search_projects": RiskTier.LOW,
    "get_project": RiskTier.LOW,
    "get_project_status": RiskTier.LOW,
    "update_project_status": RiskTier.MEDIUM,
}

risk_tier_for, approval_required = make_risk_lookup(_TOOL_RISK_TIERS)

__all__ = ["RiskTier", "approval_required", "risk_tier_for"]
