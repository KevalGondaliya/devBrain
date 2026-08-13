"""GitHub business logic: search/get issues, PRs, commits, repository
activity, per `DevBrain_vision.md` §11.4.

Depends only on the `GithubAdapter` Protocol (`adapters/protocol.py`), never
on `FakeGithubAdapter`/`RealGithubAdapter` directly — `get_adapter()` below
is the single factory function that decides which concrete adapter backs a
call. Swapping fake -> real (DevBrain_vision.md §24) means changing that one
function; nothing else in this module (or `tools/github_tools.py`) needs to
change. Unit tests exploit this directly: they monkeypatch `get_adapter` to
return a hand-written double that implements the Protocol but is neither
`FakeGithubAdapter` nor `RealGithubAdapter`, proving this module only ever
calls through the Protocol's methods.

Security note (ORCHESTRATION.md): `query`/`title`/`repository` are always
treated as opaque text data — never `eval`/`exec`d or passed to a shell,
only ever persisted-as-read or ILIKE-matched inside the fake adapter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from devbrain_common.errors import NotFoundError, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from github_mcp.adapters.fake_github import FakeGithubAdapter
from github_mcp.adapters.protocol import GithubActivityRecord, GithubAdapter
from github_mcp.repositories import unit_of_work as uow

ACTIVITY_TYPES = ("commit", "pull_request", "issue", "release")


def get_adapter(session: AsyncSession) -> GithubAdapter:
    """Factory: today always returns the Postgres-backed fake adapter.

    The one-line swap for DevBrain_vision.md §24 ("Later replace the fake
    adapter with the real GitHub API"):

        return RealGithubAdapter(get_settings())

    in place of the line below — nothing else in this service (or the
    `tools/` layer above it) would need to change, since both adapters
    implement the same `GithubAdapter` Protocol.
    """
    return FakeGithubAdapter(session)


@dataclass(frozen=True)
class GithubActivityDTO:
    id: str
    project_id: str | None
    repository: str
    type: str
    title: str
    author: str | None
    url: str | None
    status: str | None
    created_at: datetime | None = None


def _record_to_dto(record: GithubActivityRecord) -> GithubActivityDTO:
    return GithubActivityDTO(
        id=str(record.id),
        project_id=str(record.project_id) if record.project_id else None,
        repository=record.repository,
        type=record.type,
        title=record.title,
        author=record.author,
        url=record.url,
        status=record.status,
        created_at=record.created_at,
    )


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError(f"{field_name!r} is not a valid UUID: {value!r}") from exc


async def search_issues(*, query: str, limit: int = 20) -> list[GithubActivityDTO]:
    if not query.strip():
        raise ValidationError("query must not be empty.")
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        records = await adapter.search_issues(query=query, limit=limit)
        return [_record_to_dto(r) for r in records]


async def get_issue(*, issue_id: str) -> GithubActivityDTO:
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        record = await adapter.get_issue(issue_id=_parse_uuid(issue_id, "id"))
        if record is None:
            raise NotFoundError(f"Issue {issue_id!r} was not found.")
        return _record_to_dto(record)


async def list_pull_requests(
    *, repository: str | None = None, status: str | None = None, limit: int = 20
) -> list[GithubActivityDTO]:
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        records = await adapter.list_pull_requests(
            repository=repository, status=status, limit=limit
        )
        return [_record_to_dto(r) for r in records]


async def get_pull_request(*, pr_id: str) -> GithubActivityDTO:
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        record = await adapter.get_pull_request(pr_id=_parse_uuid(pr_id, "id"))
        if record is None:
            raise NotFoundError(f"Pull request {pr_id!r} was not found.")
        return _record_to_dto(record)


async def search_commits(*, query: str, limit: int = 20) -> list[GithubActivityDTO]:
    if not query.strip():
        raise ValidationError("query must not be empty.")
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        records = await adapter.search_commits(query=query, limit=limit)
        return [_record_to_dto(r) for r in records]


async def get_repository_activity(*, repository: str, limit: int = 50) -> list[GithubActivityDTO]:
    if not repository.strip():
        raise ValidationError("repository must not be empty.")
    async with uow.unit_of_work() as session:
        adapter = get_adapter(session)
        records = await adapter.get_repository_activity(repository=repository, limit=limit)
        return [_record_to_dto(r) for r in records]
