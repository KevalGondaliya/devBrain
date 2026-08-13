"""Shared risk-tier vocabulary (DevBrain_vision.md §10).

Each service's own `risk.py` still owns the *data* — which of its tool
names are low/medium/high risk is genuinely service-specific and stays
listed there (see e.g. `services/task_mcp/src/task_mcp/risk.py`) — but the
`RiskTier` enum and the `risk_tier_for`/`approval_required` lookup
boilerplate around that data was byte-for-byte identical across all five
services. This module is that shared boilerplate; each service's `risk.py`
now just supplies its own `_TOOL_RISK_TIERS` dict to `make_risk_lookup`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum


class RiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def make_risk_lookup(
    tool_risk_tiers: Mapping[str, RiskTier],
) -> tuple[Callable[[str], RiskTier], Callable[[str], bool]]:
    """Return `(risk_tier_for, approval_required)` bound to one service's
    tool-name -> `RiskTier` mapping.

    `risk_tier_for` defaults unknown tool names to `RiskTier.LOW`
    (fail-open only for unknown *read* names — every write tool in a
    service is expected to be explicitly listed in its own `risk.py`).
    `approval_required` is `True` for `MEDIUM` *and* `HIGH` — Phase 6's
    approval gate (`devbrain_common.approvals`) treats both as "needs a
    human sign-off unless the caller is admin", matching
    DevBrain_vision.md §10's "Medium: approval recommended" / "High: strong
    approval or admin-only" (Phase 6 does not currently have any `HIGH`
    tool across the five servers, but the lookup handles it correctly if
    one is added).
    """

    def risk_tier_for(tool_name: str) -> RiskTier:
        return tool_risk_tiers.get(tool_name, RiskTier.LOW)

    def approval_required(tool_name: str) -> bool:
        return risk_tier_for(tool_name) in (RiskTier.MEDIUM, RiskTier.HIGH)

    return risk_tier_for, approval_required
