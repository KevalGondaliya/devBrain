"""The seam between `services/github_service.py` and where GitHub data
actually comes from (DevBrain_vision.md §21 "Adapter Architecture" +
§11.4/§24).

`GithubAdapter` is a `Protocol` (structural typing — no inheritance needed)
describing exactly the operations the service layer needs, independent of
whether the implementation reads Postgres (`FakeGithubAdapter`, what's
actually wired up today) or calls the real GitHub API
(`RealGithubAdapter`, a stub until Phase 24). `github_service.py` imports
only this Protocol and `GithubActivityRecord` — never a concrete adapter
class — so swapping fake -> real later is a one-line change in
`github_service.get_adapter()`, not a service-layer rewrite.

`GithubActivityRecord` is the shared data shape both adapters return. It is
deliberately a plain dataclass, not the SQLAlchemy `GithubActivity` ORM
model — a real GitHub-API-backed adapter will never have an ORM row to
hand back, only JSON it must translate into this same shape. Field names
match `devbrain_common.models.GithubActivity` (per DevBrain_vision.md
§17's `github_activities` table), but that's coincidence, not coupling:
`FakeGithubAdapter` does the ORM -> record translation itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class GithubActivityRecord:
    id: uuid.UUID
    project_id: uuid.UUID | None
    repository: str
    type: str  # commit | pull_request | issue | release
    title: str
    author: str | None
    url: str | None
    status: str | None
    created_at: datetime


class GithubAdapter(Protocol):
    """Structural interface every GitHub data source (fake or real) implements."""

    async def search_issues(self, *, query: str, limit: int) -> list[GithubActivityRecord]: ...

    async def get_issue(self, *, issue_id: uuid.UUID) -> GithubActivityRecord | None: ...

    async def list_pull_requests(
        self, *, repository: str | None, status: str | None, limit: int
    ) -> list[GithubActivityRecord]: ...

    async def get_pull_request(self, *, pr_id: uuid.UUID) -> GithubActivityRecord | None: ...

    async def search_commits(self, *, query: str, limit: int) -> list[GithubActivityRecord]: ...

    async def get_repository_activity(
        self, *, repository: str, limit: int
    ) -> list[GithubActivityRecord]: ...
