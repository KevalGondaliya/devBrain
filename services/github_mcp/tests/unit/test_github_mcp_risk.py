"""`github_mcp.risk` — risk-tier classification seam (DevBrain_vision.md §10)."""

from __future__ import annotations

from github_mcp.risk import RiskTier, approval_required, risk_tier_for

_ALL_TOOLS = (
    "search_issues",
    "get_issue",
    "list_pull_requests",
    "get_pull_request",
    "search_commits",
    "get_repository_activity",
)


def test_every_tool_is_low_risk_and_needs_no_approval() -> None:
    for name in _ALL_TOOLS:
        assert risk_tier_for(name) is RiskTier.LOW
        assert approval_required(name) is False


def test_unknown_tool_defaults_to_low_risk() -> None:
    assert risk_tier_for("some_future_tool") is RiskTier.LOW
