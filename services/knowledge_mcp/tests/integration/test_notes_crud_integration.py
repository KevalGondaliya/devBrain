"""Note create/get/update/delete round trip against real `db_test`.

Also exercises wikilink resolution against the Phase 2 prompt-injection
fixture note (a stable, always-present seeded note) and confirms its
instruction-shaped content is never treated as anything but data.
"""

from __future__ import annotations

import pytest
from devbrain_common.approvals import decide_approval, request_approval
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, NotFoundError
from knowledge_mcp.services import notes_service
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("patched_uow")

FIXTURE_NOTE_TITLE = "Meeting notes: vendor security questionnaire follow-up"


async def test_create_get_update_delete_round_trip(patched_uow: AsyncSession) -> None:
    created = await notes_service.create_note(
        title="Integration Test Note",
        content_md=(
            f"This note links to [[{FIXTURE_NOTE_TITLE}]] on purpose, to exercise "
            "wikilink resolution against real seeded data."
        ),
        tags=["Integration-Test-Tag"],
        note_type="technical",
        actor="integration-test",
        role=Role.ADMIN,
    )
    assert created.title == "Integration Test Note"
    assert created.slug == "integration-test-note"
    assert created.tags == ["integration-test-tag"]
    assert created.deleted_at is None

    fetched_by_id = await notes_service.get_note(note_id=created.id)
    assert fetched_by_id.id == created.id

    fetched_by_slug = await notes_service.get_note(slug=created.slug)
    assert fetched_by_slug.id == created.id

    updated = await notes_service.update_note(
        note_id=created.id,
        title="Integration Test Note (renamed)",
        tags=["Integration-Test-Tag", "second-tag"],
        actor="integration-test",
        role=Role.ADMIN,
    )
    assert updated.title == "Integration Test Note (renamed)"
    assert set(updated.tags) == {"integration-test-tag", "second-tag"}
    # slug is assigned once at creation and not recomputed on title update.
    assert updated.slug == created.slug

    # `notes.delete` is high-risk: unlike medium-risk writes, Role.ADMIN
    # alone does not bypass approval — a valid, matching approval_id is
    # required too (see knowledge_mcp/risk.py's "Decisions made").
    with pytest.raises(ApprovalRequiredError):
        await notes_service.delete_note(
            note_id=created.id, actor="integration-test", role=Role.ADMIN
        )

    approval = await request_approval(
        patched_uow,
        actor="integration-test",
        tool_name="notes.delete",
        arguments={"note_id": created.id},
        risk_tier="high",
    )
    await decide_approval(
        patched_uow, approval_id=str(approval.id), decision="approved", decided_by="admin-alice"
    )
    await notes_service.delete_note(
        note_id=created.id,
        actor="integration-test",
        role=Role.ADMIN,
        approval_id=str(approval.id),
    )

    with pytest.raises(NotFoundError):
        await notes_service.get_note(note_id=created.id)


async def test_wikilink_to_seeded_note_creates_a_real_link_row() -> None:
    from knowledge_mcp.services import links_service

    fixture = await notes_service.get_note(slug="prompt-injection-fixture-01")
    assert fixture.title == FIXTURE_NOTE_TITLE
    # Sanity: the fixture's content is data, never instructions, even though
    # this test reads/searches it just like any other note.
    assert "Ignore all previous instructions" in fixture.content

    created = await notes_service.create_note(
        title="Note Linking To The Fixture",
        content_md=f"See [[{FIXTURE_NOTE_TITLE}]] for context.",
        actor="integration-test",
        role=Role.ADMIN,
    )

    backlinks = await links_service.get_backlinks(note_id=fixture.id)
    assert any(b.source_note_id == created.id for b in backlinks)
