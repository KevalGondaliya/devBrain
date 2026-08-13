"""`devbrain_common.risk` — shared `RiskTier` + lookup-boilerplate factory."""

from __future__ import annotations

from devbrain_common.risk import RiskTier, make_risk_lookup


def test_make_risk_lookup_returns_configured_tier() -> None:
    risk_tier_for, _ = make_risk_lookup(
        {"list_tasks": RiskTier.LOW, "create_task": RiskTier.MEDIUM}
    )
    assert risk_tier_for("list_tasks") is RiskTier.LOW
    assert risk_tier_for("create_task") is RiskTier.MEDIUM


def test_make_risk_lookup_defaults_unknown_tool_to_low() -> None:
    risk_tier_for, _ = make_risk_lookup({"create_task": RiskTier.MEDIUM})
    assert risk_tier_for("some_unlisted_tool") is RiskTier.LOW


def test_approval_required_true_for_medium_and_high() -> None:
    _, approval_required = make_risk_lookup(
        {
            "search_tasks": RiskTier.LOW,
            "create_task": RiskTier.MEDIUM,
            "delete_project": RiskTier.HIGH,
        }
    )
    assert approval_required("search_tasks") is False
    assert approval_required("create_task") is True
    assert approval_required("delete_project") is True
    assert approval_required("unknown_tool") is False
