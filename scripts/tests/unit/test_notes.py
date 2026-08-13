from __future__ import annotations

from collections import Counter

from generators.notes import (
    PROMPT_INJECTION_PAYLOAD,
    PROMPT_INJECTION_SLUG,
    SECURITY_FIXTURE_TAG,
)

from ._helpers import World


def test_note_count_matches_requested_size(world: World) -> None:
    assert len(world.notes.notes) == 100  # "small" size config


def test_prompt_injection_fixture_note_exists_and_is_tagged(world: World) -> None:
    """The Phase 7 security-test lookup key: slug == PROMPT_INJECTION_SLUG
    (equivalently, the note tagged `security-fixture`). Its payload text must
    be present but framed as quoted/untrusted content, never an instruction.
    """
    fixture = next((n for n in world.notes.notes if n.slug == PROMPT_INJECTION_SLUG), None)
    assert fixture is not None
    assert fixture.id == world.notes.prompt_injection_note_id
    assert PROMPT_INJECTION_PAYLOAD in fixture.content

    tag_by_id = {t.id: t for t in world.notes.tags}
    fixture_tag_names = {
        tag_by_id[nt.tag_id].name for nt in world.notes.note_tags if nt.note_id == fixture.id
    }
    assert SECURITY_FIXTURE_TAG in fixture_tag_names


def test_duplicate_ish_notes_exist(world: World) -> None:
    """DevBrain_vision.md §16: duplicate notes — same/near-identical title,
    different timestamps.
    """
    titles = Counter(n.title for n in world.notes.notes)
    dup_titles = [title for title, c in titles.items() if c >= 2]
    assert dup_titles, "expected at least one duplicate-ish note title"

    title = dup_titles[0]
    dupes = [n for n in world.notes.notes if n.title == title]
    timestamps = {n.created_at for n in dupes}
    assert len(timestamps) == len(dupes), "duplicate notes should have distinct timestamps"


def test_tag_distribution_is_non_uniform(world: World) -> None:
    """DevBrain_vision.md §16: a handful of tags used constantly, a long tail
    used once — not a uniform distribution.
    """
    counts = Counter(nt.tag_id for nt in world.notes.note_tags)
    assert max(counts.values()) >= 5, "expected at least one heavily-reused ('hot') tag"
    assert min(counts.values()) == 1, "expected at least one single-use ('tail') tag"


def test_links_reference_real_notes(world: World) -> None:
    note_ids = {n.id for n in world.notes.notes}
    assert world.notes.links, "expected at least one wikilink to be generated"
    for link in world.notes.links:
        assert link.source_note_id in note_ids
        assert link.target_note_id in note_ids
        assert link.source_note_id != link.target_note_id


def test_note_tags_reference_real_notes_and_tags(world: World) -> None:
    note_ids = {n.id for n in world.notes.notes}
    tag_ids = {t.id for t in world.notes.tags}
    for nt in world.notes.note_tags:
        assert nt.note_id in note_ids
        assert nt.tag_id in tag_ids
