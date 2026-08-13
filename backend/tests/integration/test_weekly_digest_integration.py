"""Real `db_test` round-trip for the weekly-digest flagship path
(second-brain-mcp-plan.md §4): pulls real seeded notes (including the
prompt-injection fixture note — its `created_at` is always within the last
30 days, see `scripts/generators/notes.py`) -> summarizes via
`StubLLMClient` (deterministic, no network) -> creates a real digest note
-> the digest note's outgoing `[[wikilink]]`s resolve into real `Link` rows
back to the source notes, via the same mechanism every other note write
uses (`notes_service._relink_wikilinks`) -> a real `audit_logs` row is
written by `notes_service.create_note` itself.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from devbrain_backend.agents import weekly_digest
from devbrain_common.llm import StubLLMClient
from devbrain_common.models import AuditLog, Link, Note
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_REPO_ROOT = Path(__file__).resolve().parents[3]
_scripts_dir = str(_REPO_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from generators.notes import PROMPT_INJECTION_SLUG  # noqa: E402 - sys.path set above

# Guarantees the seeded prompt-injection fixture note is included: its
# `created_at` is always `now - randint(1, 30)` days (see
# scripts/generators/notes.py), so any window >= 31 days always covers it,
# independent of the random offset actually rolled for this seed.
_SINCE_DAYS = 31


async def test_weekly_digest_creates_note_linked_to_sources(patched_uow: AsyncSession) -> None:
    result = await weekly_digest.generate_weekly_digest(
        actor="tester", since_days=_SINCE_DAYS, llm=StubLLMClient()
    )

    assert result.source_note_count >= 1
    assert result.digest_note.id
    assert weekly_digest.DIGEST_TAG in result.digest_note.tags

    # The digest note round-trips through the real repository/DB layer.
    persisted = await patched_uow.get(Note, uuid.UUID(result.digest_note.id))
    assert persisted is not None
    assert persisted.title == result.digest_note.title

    # Outgoing links were created back to (at least some of) the source
    # notes via the pre-existing `[[wikilink]]` -> `Link` mechanism — no
    # new links-writing code was added for this orchestrator.
    outgoing = await patched_uow.execute(
        select(Link).where(Link.source_note_id == result.digest_note.id)
    )
    outgoing_links = outgoing.scalars().all()
    assert len(outgoing_links) >= 1
    linked_target_ids = {link.target_note_id for link in outgoing_links}
    all_note_ids = {row[0] for row in (await patched_uow.execute(select(Note.id))).all()}
    assert linked_target_ids.issubset(all_note_ids)

    # `notes_service.create_note` wrote its own audit row — the same audit
    # trail a direct `notes.create` MCP tool call would produce.
    audit_rows = await patched_uow.execute(
        select(AuditLog).where(AuditLog.tool_name == "notes.create")
    )
    digest_title = result.digest_note.title
    assert any(row.arguments.get("title") == digest_title for row in audit_rows.scalars())


async def test_weekly_digest_includes_prompt_injection_fixture_note(
    patched_uow: AsyncSession,
) -> None:
    """The fixture note is real, seeded content — this proves the agent's
    real read path (`notes_service.list_recent_notes`) picks it up exactly
    like any other note, with no special-casing anywhere."""
    result = await weekly_digest.generate_weekly_digest(
        actor="tester", since_days=_SINCE_DAYS, llm=StubLLMClient()
    )
    fixture_note = await patched_uow.execute(select(Note).where(Note.slug == PROMPT_INJECTION_SLUG))
    fixture = fixture_note.scalar_one()
    assert fixture.title in result.source_note_titles
