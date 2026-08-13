"""`FakeGithubAdapter` — the ORM-row -> `GithubActivityRecord` translation,
with `repositories.github_activities_repository` mocked out (no DB)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from github_mcp.adapters import fake_github


@dataclass
class FakeRow:
    id: uuid.UUID
    project_id: uuid.UUID | None
    repository: str
    type: str
    title: str
    author: str | None = None
    url: str | None = None
    status: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


async def test_search_issues_delegates_to_repository_with_type_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def fake_search(
        session: object, *, query: str, type_: str | None, limit: int
    ) -> list[FakeRow]:
        seen.update({"query": query, "type_": type_, "limit": limit})
        return [FakeRow(id=uuid.uuid4(), project_id=None, repository="r", type="issue", title="t")]

    monkeypatch.setattr(fake_github.github_activities_repository, "search", fake_search)

    adapter = fake_github.FakeGithubAdapter(session=object())  # type: ignore[arg-type]
    results = await adapter.search_issues(query="bug", limit=10)

    assert seen == {"query": "bug", "type_": "issue", "limit": 10}
    assert results[0].title == "t"


async def test_get_issue_returns_none_when_type_mismatches(monkeypatch: pytest.MonkeyPatch) -> None:
    activity_id = uuid.uuid4()

    async def fake_get_by_id(session: object, aid: uuid.UUID) -> FakeRow:
        return FakeRow(
            id=aid, project_id=None, repository="r", type="pull_request", title="not an issue"
        )

    monkeypatch.setattr(fake_github.github_activities_repository, "get_by_id", fake_get_by_id)

    adapter = fake_github.FakeGithubAdapter(session=object())  # type: ignore[arg-type]
    result = await adapter.get_issue(issue_id=activity_id)
    assert result is None


async def test_get_issue_returns_record_when_type_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    activity_id = uuid.uuid4()

    async def fake_get_by_id(session: object, aid: uuid.UUID) -> FakeRow:
        return FakeRow(id=aid, project_id=None, repository="r", type="issue", title="a real issue")

    monkeypatch.setattr(fake_github.github_activities_repository, "get_by_id", fake_get_by_id)

    adapter = fake_github.FakeGithubAdapter(session=object())  # type: ignore[arg-type]
    result = await adapter.get_issue(issue_id=activity_id)
    assert result is not None
    assert result.title == "a real issue"
    assert result.id == activity_id


async def test_get_issue_returns_none_when_row_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_id(session: object, aid: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(fake_github.github_activities_repository, "get_by_id", fake_get_by_id)

    adapter = fake_github.FakeGithubAdapter(session=object())  # type: ignore[arg-type]
    result = await adapter.get_issue(issue_id=uuid.uuid4())
    assert result is None


async def test_list_pull_requests_delegates_with_pull_request_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def fake_list_by_filters(
        session: object,
        *,
        repository: str | None = None,
        type_: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[FakeRow]:
        seen.update({"repository": repository, "type_": type_, "status": status, "limit": limit})
        return []

    monkeypatch.setattr(
        fake_github.github_activities_repository, "list_by_filters", fake_list_by_filters
    )

    adapter = fake_github.FakeGithubAdapter(session=object())  # type: ignore[arg-type]
    await adapter.list_pull_requests(repository="devbrain/devbrain", status="open", limit=5)

    assert seen == {
        "repository": "devbrain/devbrain",
        "type_": "pull_request",
        "status": "open",
        "limit": 5,
    }


async def test_get_repository_activity_has_no_type_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    async def fake_list_by_filters(
        session: object,
        *,
        repository: str | None = None,
        type_: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[FakeRow]:
        seen.update({"repository": repository, "type_": type_})
        return []

    monkeypatch.setattr(
        fake_github.github_activities_repository, "list_by_filters", fake_list_by_filters
    )

    adapter = fake_github.FakeGithubAdapter(session=object())  # type: ignore[arg-type]
    await adapter.get_repository_activity(repository="devbrain/devbrain", limit=50)

    assert seen == {"repository": "devbrain/devbrain", "type_": None}
