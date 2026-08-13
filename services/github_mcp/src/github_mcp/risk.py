"""Risk-tier classification for this service's tools (DevBrain_vision.md §10).

- **Low** (read-only, auto-executed): every tool in this service —
  `search_issues`, `get_issue`, `list_pull_requests`, `get_pull_request`,
  `search_commits`, `get_repository_activity`. `DevBrain_vision.md` §11.4
  lists no write tool for GitHub MCP (it's a fake/synthetic-data,
  read-only server today; a real write path, e.g. commenting on an issue,
  is out of scope until Phase 24's real-integration swap).
- **Medium/High**: none in this service's tool surface, so nothing here
  goes through Phase 6's approval gate (`devbrain_common.approvals`).

The `RiskTier` enum and the `risk_tier_for`/`approval_required` lookup
boilerplate are shared (`devbrain_common.risk.make_risk_lookup`) — this
module's own job is just the tool-name -> tier data, kept for symmetry
with every sibling MCP server even though nothing here is medium/high.
"""

from __future__ import annotations

from devbrain_common.risk import RiskTier, make_risk_lookup

_TOOL_RISK_TIERS: dict[str, RiskTier] = {
    "search_issues": RiskTier.LOW,
    "get_issue": RiskTier.LOW,
    "list_pull_requests": RiskTier.LOW,
    "get_pull_request": RiskTier.LOW,
    "search_commits": RiskTier.LOW,
    "get_repository_activity": RiskTier.LOW,
}

risk_tier_for, approval_required = make_risk_lookup(_TOOL_RISK_TIERS)

__all__ = ["RiskTier", "approval_required", "risk_tier_for"]
