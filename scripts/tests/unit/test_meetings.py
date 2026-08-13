from __future__ import annotations

from generators.common import utcnow

from ._helpers import World


def test_meeting_count_matches_requested_size(world: World) -> None:
    assert len(world.meetings.meetings) == 20  # "small" size config


def test_renamed_project_old_name_appears_in_an_older_meeting(world: World) -> None:
    """DevBrain_vision.md §16 messiness: a renamed project's old name shows up
    in an older meeting's text even though `projects.name` is now different.
    """
    _project_id, old_name = next(iter(world.projects.renamed.items()))
    matches = [
        m
        for m in world.meetings.meetings
        if old_name in (m.title or "") or old_name in (m.summary or "")
    ]
    assert matches, "expected at least one meeting referencing the old project name"
    # it should genuinely be an *old* meeting (near the 730-day-back horizon),
    # not just any meeting that happens to mention the old name.
    now = utcnow()
    assert all((now - m.date).days > 600 for m in matches)
