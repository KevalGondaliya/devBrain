"""The adapter actually wired up today: a thin wrapper over the Postgres
`github_activities` table (`repositories/github_activities_repository.py`),
implementing the `GithubAdapter` Protocol (`adapters/protocol.py`).

"Fake" refers to the *data* (synthetic/Faker-generated, per
`scripts/generators/github_activity.py`), not the code path — every query
here is a real, parameterized SQLAlchemy ORM query against a real Postgres
table. DevBrain_vision.md §11.4: "Initially use fake GitHub data ... Later
replace the fake adapter with the real GitHub API." This is that "fake
adapter".
"""

from __future__ import annotations

import uuid

from devbrain_common.models import GithubActivity
from sqlalchemy.ext.asyncio import AsyncSession

from github_mcp.adapters.protocol import GithubActivityRecord
from github_mcp.repositories import github_activities_repository as github_activities_repository


def _to_record(row: GithubActivity) -> GithubActivityRecord:
    return GithubActivityRecord(
        id=row.id,
        project_id=row.project_id,
        repository=row.repository,
        type=row.type,
        title=row.title,
        author=row.author,
        url=row.url,
        status=row.status,
        created_at=row.created_at,
    )


class FakeGithubAdapter:
    """Postgres-backed `GithubAdapter` implementation. See module docstring."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_issues(self, *, query: str, limit: int) -> list[GithubActivityRecord]:
        rows = await github_activities_repository.search(
            self._session, query=query, type_="issue", limit=limit
        )
        return [_to_record(r) for r in rows]

    async def get_issue(self, *, issue_id: uuid.UUID) -> GithubActivityRecord | None:
        row = await github_activities_repository.get_by_id(self._session, issue_id)
        if row is None or row.type != "issue":
            return None
        return _to_record(row)

    async def list_pull_requests(
        self, *, repository: str | None, status: str | None, limit: int
    ) -> list[GithubActivityRecord]:
        rows = await github_activities_repository.list_by_filters(
            self._session,
            repository=repository,
            type_="pull_request",
            status=status,
            limit=limit,
        )
        return [_to_record(r) for r in rows]

    async def get_pull_request(self, *, pr_id: uuid.UUID) -> GithubActivityRecord | None:
        row = await github_activities_repository.get_by_id(self._session, pr_id)
        if row is None or row.type != "pull_request":
            return None
        return _to_record(row)

    async def search_commits(self, *, query: str, limit: int) -> list[GithubActivityRecord]:
        rows = await github_activities_repository.search(
            self._session, query=query, type_="commit", limit=limit
        )
        return [_to_record(r) for r in rows]

    async def get_repository_activity(
        self, *, repository: str, limit: int
    ) -> list[GithubActivityRecord]:
        rows = await github_activities_repository.list_by_filters(
            self._session, repository=repository, limit=limit
        )
        return [_to_record(r) for r in rows]
