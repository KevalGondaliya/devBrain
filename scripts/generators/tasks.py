"""Task generation (DevBrain_vision.md §13 step 5, §16 messiness).

Covers: overdue tasks (past `due_date`, still open), genuinely completed
tasks, cancelled tasks, and blocked tasks with a `blocked_reason` — plus some
task titles that read as if they came straight out of a decision (matching
the §13 dependency-chain example: Decision "Use scoped OAuth" -> Task
"Implement OAuth").
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta

from devbrain_common.models import Decision, Project, Task
from faker import Faker

from .common import utcnow
from .people import Person

STATUSES = ("todo", "in_progress", "blocked", "done", "cancelled")
STATUS_WEIGHTS = (0.25, 0.25, 0.1, 0.3, 0.1)
PRIORITIES = ("low", "medium", "high", "critical")
PRIORITY_WEIGHTS = (0.25, 0.4, 0.25, 0.1)

BLOCKED_REASONS = (
    "Waiting on API access from a third party.",
    "Blocked on the auth architecture decision.",
    "Needs design sign-off.",
    "Dependent task not yet finished.",
    "Waiting on infra provisioning.",
    "Blocked on legal/compliance review.",
)

TASK_VERB_TEMPLATES = (
    "Implement {topic}",
    "Write tests for {topic}",
    "Design {topic}",
    "Fix bug in {topic}",
    "Document {topic}",
    "Review {topic}",
    "Refactor {topic}",
    "Investigate {topic}",
    "Deploy {topic}",
    "Roll out {topic}",
)

GENERIC_TOPICS = (
    "the OAuth flow",
    "the notes search index",
    "the CI pipeline",
    "the onboarding docs",
    "the calendar sync job",
    "the rate limiter",
    "the audit log viewer",
    "the embeddings pipeline",
    "the project dashboard",
    "the GitHub webhook handler",
    "the approval workflow",
    "the health-check endpoint",
)


@dataclass
class TasksResult:
    tasks: list[Task]
    overdue_task_ids: list[uuid.UUID]


def _task_title(rng: random.Random, decisions_for_project: list[Decision]) -> str:
    template = rng.choice(TASK_VERB_TEMPLATES)
    if decisions_for_project and rng.random() < 0.4:
        topic = decisions_for_project[rng.randrange(len(decisions_for_project))].title.lower()
    else:
        topic = rng.choice(GENERIC_TOPICS)
    return template.format(topic=topic)


def generate_tasks(
    fake: Faker,
    rng: random.Random,
    projects: list[Project],
    decisions: list[Decision],
    people: list[Person],
    count: int,
) -> TasksResult:
    now = utcnow()
    decisions_by_project: dict[uuid.UUID, list[Decision]] = {}
    for d in decisions:
        if d.project_id is not None:
            decisions_by_project.setdefault(d.project_id, []).append(d)

    tasks: list[Task] = []
    overdue_ids: list[uuid.UUID] = []

    # Guarantee a minimum number of genuinely overdue tasks regardless of
    # dataset size, per DevBrain_vision.md §16.
    min_overdue = max(2, count // 20) if count else 0

    for i in range(count):
        project = rng.choice(projects)
        due_date = None

        if i < min_overdue:
            status = rng.choice(("todo", "in_progress", "blocked"))
            due_date = now - timedelta(days=rng.randint(1, 120))
        else:
            status = rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
            if status == "done":
                due_date = now - timedelta(days=rng.randint(0, 200)) if rng.random() < 0.7 else None
            elif status == "cancelled":
                due_date = now - timedelta(days=rng.randint(0, 150)) if rng.random() < 0.5 else None
            else:
                # todo/in_progress/blocked: mostly a future due date, but some
                # organically overdue too (not every overdue task comes from
                # the forced minimum above), and some with no due date at all.
                roll = rng.random()
                if roll < 0.25:
                    due_date = now - timedelta(days=rng.randint(1, 90))
                elif roll < 0.9:
                    due_date = now + timedelta(days=rng.randint(1, 120))
                else:
                    due_date = None

        blocked_reason = rng.choice(BLOCKED_REASONS) if status == "blocked" else None
        title = _task_title(rng, decisions_by_project.get(project.id, []))
        task = Task(
            id=uuid.uuid4(),
            project_id=project.id,
            title=title,
            description=fake.sentence(nb_words=12) if rng.random() < 0.85 else None,
            status=status,
            priority=rng.choices(PRIORITIES, weights=PRIORITY_WEIGHTS, k=1)[0],
            assignee=rng.choice(people).name if people and rng.random() < 0.9 else None,
            due_date=due_date,
            blocked_reason=blocked_reason,
        )
        tasks.append(task)
        if due_date is not None and due_date < now and status in ("todo", "in_progress", "blocked"):
            overdue_ids.append(task.id)

    return TasksResult(tasks=tasks, overdue_task_ids=overdue_ids)
