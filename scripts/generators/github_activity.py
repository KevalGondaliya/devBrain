"""GitHub activity generation (DevBrain_vision.md §13 step 7)."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta

from devbrain_common.models import GithubActivity, Project, Task
from faker import Faker

from .common import random_datetime_between, slugify, utcnow
from .people import Person

TYPES = ("commit", "pull_request", "issue", "release")
TYPE_WEIGHTS = (0.55, 0.25, 0.15, 0.05)

PR_STATUSES = ("open", "merged", "closed")
ISSUE_STATUSES = ("open", "closed")
COMMIT_PREFIXES = ("fix", "feat", "chore", "refactor", "test", "docs")


@dataclass
class GithubActivitiesResult:
    activities: list[GithubActivity]


def _repo_for_project(project: Project | None, fake: Faker) -> str:
    if project:
        return f"devbrain-org/{slugify(project.name)}"
    return f"devbrain-org/{slugify(fake.word())}-tools"


def generate_github_activities(
    fake: Faker,
    rng: random.Random,
    projects: list[Project],
    tasks: list[Task],
    people: list[Person],
    count: int,
) -> GithubActivitiesResult:
    now = utcnow()
    earliest = now - timedelta(days=400)
    tasks_by_project: dict[uuid.UUID, list[Task]] = {}
    for t in tasks:
        tasks_by_project.setdefault(t.project_id, []).append(t)

    activities: list[GithubActivity] = []
    for _ in range(count):
        project = rng.choice(projects) if projects and rng.random() < 0.85 else None
        activity_type = rng.choices(TYPES, weights=TYPE_WEIGHTS, k=1)[0]
        candidate_tasks = tasks_by_project.get(project.id, []) if project else []
        task = rng.choice(candidate_tasks) if candidate_tasks and rng.random() < 0.5 else None

        base_title = task.title if task else fake.sentence(nb_words=6).rstrip(".")
        title = (
            f"{rng.choice(COMMIT_PREFIXES)}: {base_title.lower()}"
            if activity_type == "commit"
            else base_title
        )

        status = None
        if activity_type == "pull_request":
            status = rng.choice(PR_STATUSES)
        elif activity_type == "issue":
            status = rng.choice(ISSUE_STATUSES)

        repository = _repo_for_project(project, fake)
        if activity_type == "commit":
            kind_segment = "commit"
        elif activity_type == "pull_request":
            kind_segment = "pull"
        else:
            kind_segment = "issues"
        activities.append(
            GithubActivity(
                id=uuid.uuid4(),
                project_id=project.id if project else None,
                repository=repository,
                type=activity_type,
                title=title,
                author=rng.choice(people).name if people else None,
                url=f"https://github.com/{repository}/{kind_segment}/{rng.randint(1, 9999)}",
                status=status,
                created_at=random_datetime_between(rng, earliest, now),
            )
        )
    return GithubActivitiesResult(activities=activities)
