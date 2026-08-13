from __future__ import annotations

from generators.decisions import CONFLICTING_TITLE

from ._helpers import World


def test_decision_count_matches_requested_size(world: World) -> None:
    assert len(world.decisions.decisions) == 50  # "small" size config


def test_conflicting_decision_pair_exists(world: World) -> None:
    """DevBrain_vision.md §16: same-topic decisions at different dates with
    different statuses, so a reader must use recency/status — not just
    "the first result" — to answer "what's the current decision?".
    """
    same_topic = [d for d in world.decisions.decisions if d.title == CONFLICTING_TITLE]
    assert len(same_topic) >= 2

    older, newer = sorted(same_topic, key=lambda d: d.date)[:2]
    assert older.date < newer.date
    assert older.decision != newer.decision
    assert older.status == "superseded"
    assert newer.status == "accepted"
    assert "mongodb" in older.decision.lower()
    assert "postgresql" in newer.decision.lower()

    ids = {d.id for d in (older, newer)}
    assert ids == set(world.decisions.conflicting_pair_ids)
