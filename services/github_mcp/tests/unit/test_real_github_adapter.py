"""`RealGithubAdapter` — confirms it satisfies the same call shape as
`FakeGithubAdapter` (constructible, same method signatures) while every
operation is a deliberate `NotImplementedError` stub (Phase 24 not built
yet)."""

from __future__ import annotations

import uuid

import pytest
from github_mcp.adapters.real_github import RealGithubAdapter


def test_constructible_with_arbitrary_args() -> None:
    # The whole point of the stub: constructing it doesn't blow up, so the
    # one-line factory swap in github_service.get_adapter() type-checks and
    # runs today even though no method is implemented yet.
    RealGithubAdapter()
    RealGithubAdapter("some-client", token="abc")


@pytest.mark.parametrize(
    "call",
    [
        lambda a: a.search_issues(query="x", limit=1),
        lambda a: a.get_issue(issue_id=uuid.uuid4()),
        lambda a: a.list_pull_requests(repository=None, status=None, limit=1),
        lambda a: a.get_pull_request(pr_id=uuid.uuid4()),
        lambda a: a.search_commits(query="x", limit=1),
        lambda a: a.get_repository_activity(repository="r", limit=1),
    ],
)
async def test_every_method_raises_not_implemented(call: object) -> None:
    adapter = RealGithubAdapter()
    with pytest.raises(NotImplementedError):
        await call(adapter)  # type: ignore[operator]
