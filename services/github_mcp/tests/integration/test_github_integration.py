"""Real `db_test` round-trips against Phase 2's `--size small --seed 42` seed."""

from __future__ import annotations

import uuid

import pytest
from devbrain_common.errors import NotFoundError
from devbrain_common.models import GithubActivity
from github_mcp.services import github_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _a_real_activity(db_session: AsyncSession, type_: str) -> GithubActivity:
    result = await db_session.execute(
        select(GithubActivity).where(GithubActivity.type == type_).limit(1)
    )
    return result.scalars().one()


async def test_search_issues_finds_a_real_issue_by_title_fragment(
    patched_uow: AsyncSession,
) -> None:
    issue = await _a_real_activity(patched_uow, "issue")
    fragment = issue.title.split()[0]

    results = await github_service.search_issues(query=fragment)
    assert any(r.id == str(issue.id) for r in results)


async def test_get_issue_roundtrip(patched_uow: AsyncSession) -> None:
    issue = await _a_real_activity(patched_uow, "issue")

    dto = await github_service.get_issue(issue_id=str(issue.id))
    assert dto.id == str(issue.id)
    assert dto.type == "issue"


async def test_get_issue_wrong_type_raises_not_found(patched_uow: AsyncSession) -> None:
    commit = await _a_real_activity(patched_uow, "commit")

    with pytest.raises(NotFoundError):
        await github_service.get_issue(issue_id=str(commit.id))


async def test_get_issue_unknown_id_raises_not_found(patched_uow: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await github_service.get_issue(issue_id=str(uuid.uuid4()))


async def test_list_pull_requests_filters_by_repository(patched_uow: AsyncSession) -> None:
    pr = await _a_real_activity(patched_uow, "pull_request")

    results = await github_service.list_pull_requests(repository=pr.repository)
    assert all(r.repository == pr.repository for r in results)
    assert any(r.id == str(pr.id) for r in results)


async def test_get_pull_request_roundtrip(patched_uow: AsyncSession) -> None:
    pr = await _a_real_activity(patched_uow, "pull_request")

    dto = await github_service.get_pull_request(pr_id=str(pr.id))
    assert dto.id == str(pr.id)
    assert dto.type == "pull_request"


async def test_search_commits_finds_a_real_commit(patched_uow: AsyncSession) -> None:
    commit = await _a_real_activity(patched_uow, "commit")
    # Commit titles are "prefix: <lowercased base title>" (see
    # scripts/generators/github_activity.py) — search on a body word.
    fragment = commit.title.split(": ", 1)[-1].split()[0]

    results = await github_service.search_commits(query=fragment)
    assert any(r.id == str(commit.id) for r in results)


async def test_get_repository_activity_returns_only_that_repository(
    patched_uow: AsyncSession,
) -> None:
    activity = await _a_real_activity(patched_uow, "release")

    results = await github_service.get_repository_activity(repository=activity.repository)
    assert results
    assert all(r.repository == activity.repository for r in results)
