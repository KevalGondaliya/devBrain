"""SQLAlchemy ORM models for the full DevBrain schema.

Schema sources (see ORCHESTRATION.md for precedence rules):
  - `docs/planning/DevBrain_vision.md` §17 (core tables: users, projects,
    tasks, meetings, decisions, notes, github_activities, calendar_events,
    approvals, audit_logs)
  - `docs/planning/second-brain-mcp-plan.md` §3 (Knowledge MCP additions:
    tags, note_tags, links, embeddings; notes gains slug + soft-delete)

Design decisions (see PROGRESS_REPORT.md Phase 1 "Decisions made" for the
authoritative copy):
  - **Primary keys are UUIDv4** (Postgres native `UUID`, generated
    client-side via `uuid.uuid4`, not `gen_random_uuid()`) for every table.
    This avoids depending on the `pgcrypto`/`pgcrypto`-adjacent extensions
    and keeps IDs generatable before insert (useful for tests and for the
    audit/approval flow needing a stable ID up front).
  - **Timestamps are always timezone-aware** (`TIMESTAMPTZ`), defaulted at
    the database via `func.now()`.
  - **Status/type/role vocabularies** are plain `String` columns validated
    at the Pydantic/service layer (per ORCHESTRATION.md "every tool input is
    a Pydantic model"), reinforced at the DB layer with `CHECK` constraints
    for defense-in-depth. Postgres native ENUM types were deliberately
    avoided — adding a new status value would require `ALTER TYPE`
    migrations, which is friction we don't need for a schema still settling
    across phases.
  - `owner` (Project) and `assignee` (Task) are free-text name columns
    matching the DevBrain_vision.md §17 field list exactly (not FKs to
    `users`) — `users` exists primarily to back MCP actor identity/auth, not
    to normalize every human-name field in the seed data.
  - Cross-entity link columns (`project_id` on meetings/decisions/notes/
    github_activities/calendar_events, `meeting_id` on decisions) are
    nullable: not every note or GitHub activity is tied to a project.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from devbrain_common.db import Base

EMBEDDING_DIM = 384


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """created_at / updated_at, both timezone-aware, server-defaulted."""

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------
# Auth / actors
# --------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role in ('viewer','user','admin')", name="ck_users_role"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(nullable=False, unique=True)
    role: Mapped[str] = mapped_column(nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


# --------------------------------------------------------------------------
# Projects / Tasks / Meetings / Decisions
# --------------------------------------------------------------------------


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "status in ('planned','active','blocked','completed','archived')",
            name="ck_projects_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(nullable=False, default="planned", index=True)
    priority: Mapped[str | None] = mapped_column(default=None)
    start_date: Mapped[datetime | None] = mapped_column(default=None)
    target_date: Mapped[datetime | None] = mapped_column(default=None)
    owner: Mapped[str | None] = mapped_column(default=None)

    tasks: Mapped[list[Task]] = relationship(back_populates="project", cascade="all, delete-orphan")
    meetings: Mapped[list[Meeting]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    decisions: Mapped[list[Decision]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    notes: Mapped[list[Note]] = relationship(back_populates="project", cascade="all, delete-orphan")
    github_activities: Mapped[list[GithubActivity]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    calendar_events: Mapped[list[CalendarEvent]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status in ('todo','in_progress','blocked','done','cancelled')",
            name="ck_tasks_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(nullable=False, default="todo", index=True)
    priority: Mapped[str | None] = mapped_column(default=None)
    assignee: Mapped[str | None] = mapped_column(default=None)
    due_date: Mapped[datetime | None] = mapped_column(default=None)
    blocked_reason: Mapped[str | None] = mapped_column(default=None)

    project: Mapped[Project] = relationship(back_populates="tasks")


class Meeting(Base, TimestampMixin):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(nullable=False)
    date: Mapped[datetime] = mapped_column(nullable=False, index=True)
    duration_minutes: Mapped[int | None] = mapped_column(default=None)
    participants: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    summary: Mapped[str | None] = mapped_column(default=None)
    transcript_path: Mapped[str | None] = mapped_column(default=None)

    project: Mapped[Project | None] = relationship(back_populates="meetings")
    decisions: Mapped[list[Decision]] = relationship(back_populates="meeting")


class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(
            "status in ('proposed','accepted','rejected','superseded')",
            name="ck_decisions_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(nullable=False)
    decision: Mapped[str] = mapped_column(nullable=False)
    reasoning: Mapped[str | None] = mapped_column(default=None)
    date: Mapped[datetime] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(nullable=False, default="proposed", index=True)

    project: Mapped[Project | None] = relationship(back_populates="decisions")
    meeting: Mapped[Meeting | None] = relationship(back_populates="decisions")


# --------------------------------------------------------------------------
# Knowledge MCP: notes, tags, links, embeddings
# --------------------------------------------------------------------------


class Note(Base, TimestampMixin):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "type in ('learning','architecture','technical','idea','personal')",
            name="ck_notes_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(nullable=False, unique=True, index=True)
    content: Mapped[str] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(nullable=False, default="technical", index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None, index=True)

    project: Mapped[Project | None] = relationship(back_populates="notes")
    note_tags: Mapped[list[NoteTag]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )
    embeddings: Mapped[list[Embedding]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )
    outgoing_links: Mapped[list[Link]] = relationship(
        back_populates="source_note",
        foreign_keys="Link.source_note_id",
        cascade="all, delete-orphan",
    )
    incoming_links: Mapped[list[Link]] = relationship(
        back_populates="target_note",
        foreign_keys="Link.target_note_id",
        cascade="all, delete-orphan",
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(nullable=False, unique=True, index=True)

    note_tags: Mapped[list[NoteTag]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class NoteTag(Base):
    __tablename__ = "note_tags"
    __table_args__ = (UniqueConstraint("note_id", "tag_id", name="uq_note_tags_note_tag"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True
    )

    note: Mapped[Note] = relationship(back_populates="note_tags")
    tag: Mapped[Tag] = relationship(back_populates="note_tags")


class Link(Base):
    """A wikilink `[[...]]` from one note to another."""

    __tablename__ = "links"
    __table_args__ = (Index("ix_links_source_target", "source_note_id", "target_note_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    context_snippet: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    source_note: Mapped[Note] = relationship(
        back_populates="outgoing_links", foreign_keys=[source_note_id]
    )
    target_note: Mapped[Note] = relationship(
        back_populates="incoming_links", foreign_keys=[target_note_id]
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vector: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    model_name: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )

    note: Mapped[Note] = relationship(back_populates="embeddings")


# --------------------------------------------------------------------------
# GitHub / Calendar
# --------------------------------------------------------------------------


class GithubActivity(Base):
    __tablename__ = "github_activities"
    __table_args__ = (
        CheckConstraint(
            "type in ('commit','pull_request','issue','release')",
            name="ck_github_activities_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    repository: Mapped[str] = mapped_column(nullable=False, index=True)
    type: Mapped[str] = mapped_column(nullable=False, index=True)
    title: Mapped[str] = mapped_column(nullable=False)
    author: Mapped[str | None] = mapped_column(default=None)
    url: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str | None] = mapped_column(default=None, index=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )

    project: Mapped[Project | None] = relationship(back_populates="github_activities")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(nullable=False)
    start_time: Mapped[datetime] = mapped_column(nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(nullable=False)
    participants: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    location: Mapped[str | None] = mapped_column(default=None)
    description: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    project: Mapped[Project | None] = relationship(back_populates="calendar_events")


# --------------------------------------------------------------------------
# Governance: approvals, audit log
# --------------------------------------------------------------------------


class Approval(Base):
    """Human-in-the-loop approval record for medium/high risk tool calls.

    The approval *flow* (who can decide, how a tool blocks on it) lands in
    Phase 6; this table + model exists now so the schema is stable and later
    phases only add behavior, not migrations.
    """

    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("status in ('pending','approved','rejected')", name="ck_approvals_status"),
        CheckConstraint("risk_tier in ('low','medium','high')", name="ck_approvals_risk_tier"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tool_name: Mapped[str] = mapped_column(nullable=False, index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    actor: Mapped[str] = mapped_column(nullable=False, index=True)
    risk_tier: Mapped[str] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(nullable=False, default="pending", index=True)
    requested_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(default=None)
    decided_by: Mapped[str | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(default=None)
    # Phase 6 (`devbrain_common.approvals.consume_approval`): set the first
    # (and only the first) time an *approved* approval is actually spent to
    # execute the tool call it was requested for. Separate from `status`
    # (still `approved`, not a fourth status value) so "approved but not yet
    # used" and "approved and already used" are both queryable without
    # overloading the status vocabulary / its CHECK constraint.
    consumed_at: Mapped[datetime | None] = mapped_column(default=None, index=True)


class AuditLog(Base):
    """Immutable record of every tool call. Never store secrets/raw tokens here."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("status in ('success','error','denied')", name="ck_audit_logs_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    actor: Mapped[str] = mapped_column(nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(nullable=False, index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(nullable=False, index=True)
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )
