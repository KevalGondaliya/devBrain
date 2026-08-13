from __future__ import annotations

from ._helpers import World


def test_project_count_matches_requested_size(world: World) -> None:
    assert len(world.projects.projects) == 2  # "small" size config


def test_project_names_are_unique(world: World) -> None:
    names = [p.name for p in world.projects.projects]
    assert len(names) == len(set(names))


def test_exactly_one_renamed_project_with_a_genuinely_different_old_name(
    world: World,
) -> None:
    renamed = world.projects.renamed
    assert len(renamed) == 1
    project_id, old_name = next(iter(renamed.items()))
    project = next(p for p in world.projects.projects if p.id == project_id)
    assert old_name != project.name
    assert old_name not in {p.name for p in world.projects.projects}
