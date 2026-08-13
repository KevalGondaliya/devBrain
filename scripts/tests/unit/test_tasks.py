from __future__ import annotations

from generators.common import utcnow

from ._helpers import World


def test_task_count_matches_requested_size(world: World) -> None:
    assert len(world.tasks.tasks) == 100  # "small" size config


def test_overdue_tasks_exist(world: World) -> None:
    """DevBrain_vision.md §16: some overdue tasks (due_date in the past,
    status still open).
    """
    now = utcnow()
    overdue = [
        t
        for t in world.tasks.tasks
        if t.due_date is not None
        and t.due_date < now
        and t.status in ("todo", "in_progress", "blocked")
    ]
    assert len(overdue) >= 1
    assert {t.id for t in overdue} == set(world.tasks.overdue_task_ids)


def test_completed_and_cancelled_tasks_exist(world: World) -> None:
    statuses = {t.status for t in world.tasks.tasks}
    assert "done" in statuses
    assert "cancelled" in statuses


def test_blocked_tasks_always_have_a_reason(world: World) -> None:
    blocked = [t for t in world.tasks.tasks if t.status == "blocked"]
    assert blocked, "expected at least one blocked task in this dataset"
    assert all(t.blocked_reason for t in blocked)


def test_non_blocked_tasks_have_no_blocked_reason(world: World) -> None:
    assert all(t.blocked_reason is None for t in world.tasks.tasks if t.status != "blocked")
