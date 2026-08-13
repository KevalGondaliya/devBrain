"""Decision generation (DevBrain_vision.md §13 step 4, §16 messiness)."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta

from devbrain_common.models import Decision, Meeting, Project
from faker import Faker

from .common import random_datetime_between, utcnow

STATUSES = ("proposed", "accepted", "rejected", "superseded")
STATUS_WEIGHTS = (0.15, 0.55, 0.15, 0.15)

DECISION_TOPICS = (
    ("API versioning strategy", "Use URL path versioning (/v1/...) for all public endpoints."),
    ("Frontend framework", "Adopt Next.js for the frontend."),
    ("Auth approach", "Use scoped OAuth tokens for third-party integrations."),
    ("Deployment target", "Deploy via Docker Compose for the demo environment."),
    ("Testing strategy", "Require unit and integration tests for every service."),
    ("Message queue", "Defer message-queue adoption until traffic actually requires it."),
    ("Rate limiting", "Apply a token-bucket rate limiter at the transport layer."),
    ("Logging format", "Standardize on structured JSON logs."),
    ("Monorepo tooling", "Use uv workspaces instead of separate repos per service."),
    ("Embedding model", "Use a local sentence-transformers model instead of a paid API."),
    ("CI provider", "Run CI on GitHub Actions."),
    ("Error handling", "Return structured error objects, never raw tracebacks."),
    ("Caching layer", "Skip a dedicated cache for now; Postgres is fast enough at this scale."),
    ("Notification channel", "Send digest notifications by email, not Slack, for the MVP."),
)

# The deliberate conflicting-decision pair from DevBrain_vision.md §16 —
# same topic, different dates, a reader must use recency/status to answer
# "what's the current decision?" correctly.
CONFLICTING_TITLE = "Database choice"


@dataclass
class DecisionsResult:
    decisions: list[Decision]
    conflicting_pair_ids: tuple[uuid.UUID, uuid.UUID]


def _inject_conflicting_pair(
    rng: random.Random, projects: list[Project]
) -> tuple[Decision, Decision]:
    project = rng.choice(projects)
    now = utcnow()
    early = now - timedelta(days=210)
    late = now - timedelta(days=45)
    older = Decision(
        id=uuid.uuid4(),
        project_id=project.id,
        meeting_id=None,
        title=CONFLICTING_TITLE,
        decision="Use MongoDB as the primary datastore.",
        reasoning="Flexible schema fits early prototyping speed; the team already knows Mongo.",
        date=early,
        status="superseded",
    )
    newer = Decision(
        id=uuid.uuid4(),
        project_id=project.id,
        meeting_id=None,
        title=CONFLICTING_TITLE,
        decision="PostgreSQL is now the official database.",
        reasoning=(
            "Need relational integrity, real migrations, and pgvector for embeddings; "
            "Mongo couldn't give us those."
        ),
        date=late,
        status="accepted",
    )
    return older, newer


def generate_decisions(
    fake: Faker,
    rng: random.Random,
    projects: list[Project],
    meetings: list[Meeting],
    count: int,
) -> DecisionsResult:
    now = utcnow()
    earliest = now - timedelta(days=700)
    decisions: list[Decision] = []

    older, newer = _inject_conflicting_pair(rng, projects)
    decisions.extend([older, newer])
    remaining = max(0, count - 2)

    meetings_by_project: dict[uuid.UUID | None, list[Meeting]] = {}
    for m in meetings:
        meetings_by_project.setdefault(m.project_id, []).append(m)

    for _ in range(remaining):
        project = rng.choice(projects) if projects and rng.random() < 0.85 else None
        meeting = None
        if project is not None:
            candidates = meetings_by_project.get(project.id) or []
            if candidates and rng.random() < 0.5:
                meeting = rng.choice(candidates)
        topic, decision_text = rng.choice(DECISION_TOPICS)
        date = meeting.date if meeting else random_datetime_between(rng, earliest, now)
        status = rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
        decisions.append(
            Decision(
                id=uuid.uuid4(),
                project_id=project.id if project else None,
                meeting_id=meeting.id if meeting else None,
                title=topic,
                decision=decision_text,
                # "missing fields" messiness (DevBrain_vision.md §16): not every
                # decision has recorded reasoning.
                reasoning=fake.sentence() if rng.random() < 0.8 else None,
                date=date,
                status=status,
            )
        )

    return DecisionsResult(decisions=decisions, conflicting_pair_ids=(older.id, newer.id))
