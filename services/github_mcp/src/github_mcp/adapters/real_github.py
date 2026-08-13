"""Stub for a real-GitHub-API-backed `GithubAdapter` (DevBrain_vision.md
§21 + §24 "Real Integrations": "Fake GitHub -> GitHub API").

Not implemented yet — every method raises `NotImplementedError`. This file
exists now so the *seam* is real and reviewable: `RealGithubAdapter`
implements the exact same `GithubAdapter` Protocol
(`adapters/protocol.py`) as `FakeGithubAdapter`
(`adapters/fake_github.py`), so swapping which one `github_service.py`'s
`get_adapter()` factory returns is a one-line change, not a service-layer
rewrite — the whole point of DevBrain_vision.md §21's adapter architecture.

Where a real implementation plugs in, when this is picked up:
  - `__init__` would take an authenticated GitHub client (e.g. `PyGithub`'s
    `github.Github(auth=...)` or a plain `httpx.AsyncClient` pointed at
    `https://api.github.com` with a `GITHUB_TOKEN` bearer header) — the
    token itself would be read from `devbrain_common.config.Settings`
    (a new field there, following the same pattern as `ANTHROPIC_API_KEY`),
    never hardcoded, per ORCHESTRATION.md's secrets rule.
  - Each method below would call the corresponding GitHub REST/GraphQL
    endpoint (e.g. `search_issues` -> `GET /search/issues`,
    `list_pull_requests` -> `GET /repos/{repo}/pulls`) and translate the
    JSON response into `GithubActivityRecord` instances — the same shape
    `FakeGithubAdapter` already returns, so nothing above the adapter layer
    (`github_service.py`, `tools/github_tools.py`) would need to change.
  - Real-integration-specific security concerns (DevBrain_vision.md §22):
    OAuth/token rotation, SSRF protection on any user-influenced URL
    construction, and network egress rules would all be handled inside
    this adapter, not leaked into the service layer.
"""

from __future__ import annotations

import uuid

from github_mcp.adapters.protocol import GithubActivityRecord

_NOT_IMPLEMENTED = (
    "RealGithubAdapter is a Phase 24 stub — the live GitHub API integration "
    "has not been built yet. FakeGithubAdapter (Postgres-backed synthetic "
    "data) is what's actually wired up today; see github_service.get_adapter()."
)


class RealGithubAdapter:
    """Not-yet-implemented `GithubAdapter` over the real GitHub API. See module docstring.

    `__init__` deliberately does *not* raise — it accepts (and ignores) the
    future client/settings args so the one-line swap in
    `github_service.get_adapter()` (`return RealGithubAdapter(...)` instead
    of `FakeGithubAdapter(session)`) is a real, type-checkable statement
    today, not just a comment. Every actual operation raises
    `NotImplementedError` when called.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def search_issues(self, *, query: str, limit: int) -> list[GithubActivityRecord]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    async def get_issue(self, *, issue_id: uuid.UUID) -> GithubActivityRecord | None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    async def list_pull_requests(
        self, *, repository: str | None, status: str | None, limit: int
    ) -> list[GithubActivityRecord]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    async def get_pull_request(self, *, pr_id: uuid.UUID) -> GithubActivityRecord | None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    async def search_commits(self, *, query: str, limit: int) -> list[GithubActivityRecord]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    async def get_repository_activity(
        self, *, repository: str, limit: int
    ) -> list[GithubActivityRecord]:
        raise NotImplementedError(_NOT_IMPLEMENTED)
