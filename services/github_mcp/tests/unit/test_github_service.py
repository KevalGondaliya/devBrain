"""`github_service` orchestration — the adapter is mocked out via
`get_adapter`, and deliberately *not* `FakeGithubAdapter`: `DoubleAdapter`
below is a hand-written double that implements the `GithubAdapter` Protocol
on its own terms (no shared base class, no import of `FakeGithubAdapter` at
all). If these tests pass, `github_service` genuinely only depends on the
Protocol's shape, not on any concrete adapter class — proving the fake/real
adapter seam described in `adapters/protocol.py`'s module docstring is real,
not just documented.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from devbrain_common.errors import NotFoundError, ValidationError
from github_mcp.adapters.protocol import GithubActivityRecord
from github_mcp.services import github_service


@dataclass
class DoubleAdapter:
    """A `GithubAdapter`-shaped double independent of `FakeGithubAdapter`."""

    issues: list[GithubActivityRecord] = field(default_factory=list)
    prs: list[GithubActivityRecord] = field(default_factory=list)
    commits: list[GithubActivityRecord] = field(default_factory=list)
    activity: list[GithubActivityRecord] = field(default_factory=list)
    by_id: dict[uuid.UUID, GithubActivityRecord] = field(default_factory=dict)
    seen_calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    async def search_issues(self, *, query: str, limit: int) -> list[GithubActivityRecord]:
        self.seen_calls.append(("search_issues", {"query": query, "limit": limit}))
        return self.issues

    async def get_issue(self, *, issue_id: uuid.UUID) -> GithubActivityRecord | None:
        self.seen_calls.append(("get_issue", {"issue_id": issue_id}))
        row = self.by_id.get(issue_id)
        return row if row is not None and row.type == "issue" else None

    async def list_pull_requests(
        self, *, repository: str | None, status: str | None, limit: int
    ) -> list[GithubActivityRecord]:
        self.seen_calls.append(
            ("list_pull_requests", {"repository": repository, "status": status, "limit": limit})
        )
        return self.prs

    async def get_pull_request(self, *, pr_id: uuid.UUID) -> GithubActivityRecord | None:
        self.seen_calls.append(("get_pull_request", {"pr_id": pr_id}))
        row = self.by_id.get(pr_id)
        return row if row is not None and row.type == "pull_request" else None

    async def search_commits(self, *, query: str, limit: int) -> list[GithubActivityRecord]:
        self.seen_calls.append(("search_commits", {"query": query, "limit": limit}))
        return self.commits

    async def get_repository_activity(
        self, *, repository: str, limit: int
    ) -> list[GithubActivityRecord]:
        self.seen_calls.append(
            ("get_repository_activity", {"repository": repository, "limit": limit})
        )
        return self.activity


def _record(**overrides: object) -> GithubActivityRecord:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "project_id": None,
        "repository": "devbrain/devbrain",
        "type": "issue",
        "title": "Fix the thing",
        "author": "octocat",
        "url": "https://github.com/devbrain/devbrain/issues/1",
        "status": "open",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return GithubActivityRecord(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def double(monkeypatch: pytest.MonkeyPatch) -> DoubleAdapter:
    adapter = DoubleAdapter()

    def fake_get_adapter(session: object) -> DoubleAdapter:
        return adapter

    monkeypatch.setattr(github_service, "get_adapter", fake_get_adapter)
    return adapter


async def test_search_issues_rejects_empty_query(double: DoubleAdapter) -> None:
    with pytest.raises(ValidationError):
        await github_service.search_issues(query="   ")


async def test_search_issues_returns_dtos(double: DoubleAdapter) -> None:
    double.issues = [_record(title="Login bug")]
    results = await github_service.search_issues(query="login")
    assert results[0].title == "Login bug"
    assert double.seen_calls[0] == ("search_issues", {"query": "login", "limit": 20})


async def test_get_issue_not_found_raises(double: DoubleAdapter) -> None:
    with pytest.raises(NotFoundError):
        await github_service.get_issue(issue_id=str(uuid.uuid4()))


async def test_get_issue_invalid_uuid_raises_validation_error(double: DoubleAdapter) -> None:
    with pytest.raises(ValidationError):
        await github_service.get_issue(issue_id="not-a-uuid")


async def test_get_issue_found_returns_dto(double: DoubleAdapter) -> None:
    issue_id = uuid.uuid4()
    double.by_id[issue_id] = _record(id=issue_id, type="issue", title="Real issue")
    dto = await github_service.get_issue(issue_id=str(issue_id))
    assert dto.title == "Real issue"
    assert dto.id == str(issue_id)


async def test_list_pull_requests_passes_filters_through(double: DoubleAdapter) -> None:
    double.prs = [_record(type="pull_request", title="Add feature")]
    results = await github_service.list_pull_requests(repository="devbrain/devbrain", status="open")
    assert results[0].title == "Add feature"
    assert double.seen_calls[0] == (
        "list_pull_requests",
        {"repository": "devbrain/devbrain", "status": "open", "limit": 20},
    )


async def test_get_pull_request_not_found_raises(double: DoubleAdapter) -> None:
    with pytest.raises(NotFoundError):
        await github_service.get_pull_request(pr_id=str(uuid.uuid4()))


async def test_search_commits_rejects_empty_query(double: DoubleAdapter) -> None:
    with pytest.raises(ValidationError):
        await github_service.search_commits(query="")


async def test_search_commits_returns_dtos(double: DoubleAdapter) -> None:
    double.commits = [_record(type="commit", title="Fix flaky test")]
    results = await github_service.search_commits(query="flaky")
    assert results[0].title == "Fix flaky test"


async def test_get_repository_activity_rejects_empty_repository(double: DoubleAdapter) -> None:
    with pytest.raises(ValidationError):
        await github_service.get_repository_activity(repository="  ")


async def test_get_repository_activity_returns_dtos(double: DoubleAdapter) -> None:
    double.activity = [_record(type="release", title="v1.0.0")]
    results = await github_service.get_repository_activity(repository="devbrain/devbrain")
    assert results[0].title == "v1.0.0"
    assert results[0].type == "release"
