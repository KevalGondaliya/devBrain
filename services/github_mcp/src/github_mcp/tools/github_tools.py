"""`search_issues`/`get_issue`/`list_pull_requests`/`get_pull_request`/
`search_commits`/`get_repository_activity` tools — `DevBrain_vision.md`
§11.4. Flat (undotted) tool names, exactly as that section names them. All
low risk (read-only, backed by fake/synthetic GitHub data today —
`services/github_service.py`'s module docstring explains the fake/real
adapter seam)."""

from __future__ import annotations

from typing import Annotated, Any

from devbrain_common.auth import Role
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from github_mcp.auth import require_min_role
from github_mcp.services import github_service
from github_mcp.tools._common import dto_to_dict, handle_tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="search_issues",
        description="Keyword search over GitHub issue title/repository/author.",
    )
    @handle_tool_errors
    async def search_issues(
        query: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        issues = await github_service.search_issues(query=query, limit=limit)
        return {"results": [dto_to_dict(i) for i in issues]}

    @mcp.tool(name="get_issue", description="Fetch a single GitHub issue by id.")
    @handle_tool_errors
    async def get_issue(id: str, ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        issue = await github_service.get_issue(issue_id=id)
        return dto_to_dict(issue)

    @mcp.tool(
        name="list_pull_requests",
        description="List pull requests, optionally filtered by repository and/or status.",
    )
    @handle_tool_errors
    async def list_pull_requests(
        repository: str | None = None,
        status: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        prs = await github_service.list_pull_requests(
            repository=repository, status=status, limit=limit
        )
        return {"pull_requests": [dto_to_dict(p) for p in prs]}

    @mcp.tool(name="get_pull_request", description="Fetch a single pull request by id.")
    @handle_tool_errors
    async def get_pull_request(
        id: str, ctx: Context[Any, Any, Any] | None = None
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        pr = await github_service.get_pull_request(pr_id=id)
        return dto_to_dict(pr)

    @mcp.tool(
        name="search_commits", description="Keyword search over commit title/repository/author."
    )
    @handle_tool_errors
    async def search_commits(
        query: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        commits = await github_service.search_commits(query=query, limit=limit)
        return {"results": [dto_to_dict(c) for c in commits]}

    @mcp.tool(
        name="get_repository_activity",
        description=(
            "List recent GitHub activity (commits, PRs, issues, releases) for one repository."
        ),
    )
    @handle_tool_errors
    async def get_repository_activity(
        repository: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        require_min_role(ctx, Role.VIEWER)
        activity = await github_service.get_repository_activity(repository=repository, limit=limit)
        return {"activity": [dto_to_dict(a) for a in activity]}
