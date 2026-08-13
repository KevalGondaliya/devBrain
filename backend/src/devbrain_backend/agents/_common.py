"""Small shared helpers for the Phase 7 orchestrators — not a service, not
a tool, just glue used only within `backend/src/devbrain_backend/agents/`.
"""

from __future__ import annotations

from github_mcp.services import github_service as github_service
from knowledge_mcp.services.notes_service import slugify


def repository_slug_for_project(project_name: str) -> str:
    """Best-effort reconstruction of a project's seeded GitHub repository
    slug, mirroring `scripts/generators/github_activity.py::_repo_for_project`
    (`devbrain-org/<slugified-project-name>`) — the seed generator's own
    naming convention, reused here rather than duplicated arbitrarily.

    This is a read-only heuristic used only to *find* relevant activity for
    an investigation/briefing orchestrator; it never gates or informs a
    write, and a wrong guess just means an empty result (no PRs found for
    that repository), never an error. `github_mcp`'s own service surface
    has no project_id -> repository lookup (`GithubActivityDTO.repository`
    is the only place the mapping lives, and there is no "list projects'
    repositories" tool), so this is the one option that doesn't require
    modifying `github_mcp` itself.
    """
    return f"devbrain-org/{slugify(project_name)}"


async def github_activity_for_project(
    project_name: str, *, pr_limit: int = 5, issue_limit: int = 5
) -> list[github_service.GithubActivityDTO]:
    """Pull requests (via the reconstructed repository slug) plus issues
    (via a plain name search, which works even when the slug guess is off)
    that look related to `project_name`. Deduplicated by id, read-only.
    """
    repository = repository_slug_for_project(project_name)
    pull_requests = await github_service.list_pull_requests(repository=repository, limit=pr_limit)
    issues = await github_service.search_issues(query=project_name, limit=issue_limit)

    seen: set[str] = set()
    merged: list[github_service.GithubActivityDTO] = []
    for item in (*pull_requests, *issues):
        if item.id not in seen:
            seen.add(item.id)
            merged.append(item)
    return merged
