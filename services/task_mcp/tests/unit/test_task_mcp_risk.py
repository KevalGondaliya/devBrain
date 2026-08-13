"""`task_mcp.risk` — risk-tier classification seam (DevBrain_vision.md §10)."""

from __future__ import annotations

from task_mcp.risk import RiskTier, approval_required, risk_tier_for


def test_read_tools_are_low_risk() -> None:
    for name in ("list_tasks", "search_tasks", "get_task"):
        assert risk_tier_for(name) is RiskTier.LOW
        assert approval_required(name) is False


def test_write_tools_are_medium_risk_and_need_approval() -> None:
    for name in ("create_task", "update_task", "complete_task"):
        assert risk_tier_for(name) is RiskTier.MEDIUM
        assert approval_required(name) is True


def test_unknown_tool_defaults_to_low_risk() -> None:
    assert risk_tier_for("some_future_tool") is RiskTier.LOW
