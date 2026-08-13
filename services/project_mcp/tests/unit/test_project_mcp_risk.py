"""`project_mcp.risk` — risk-tier classification seam (DevBrain_vision.md §10)."""

from __future__ import annotations

from project_mcp.risk import RiskTier, approval_required, risk_tier_for


def test_read_tools_are_low_risk() -> None:
    for name in ("list_projects", "search_projects", "get_project", "get_project_status"):
        assert risk_tier_for(name) is RiskTier.LOW
        assert approval_required(name) is False


def test_update_project_status_is_medium_risk_and_needs_approval() -> None:
    assert risk_tier_for("update_project_status") is RiskTier.MEDIUM
    assert approval_required("update_project_status") is True


def test_unknown_tool_defaults_to_low_risk() -> None:
    assert risk_tier_for("some_future_tool") is RiskTier.LOW
