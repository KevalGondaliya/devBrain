"""GitHub MCP — FastMCP entrypoint.

Wires config + tools. Runnable two ways:

    # stdio (local Claude Desktop/Code dev connection; no bearer auth)
    .venv/bin/python -m github_mcp.server
    .venv/bin/python -m github_mcp.server --transport stdio

    # HTTP (bearer auth enforced per-tool via github_mcp.auth; see
    # GITHUB_MCP_TRANSPORT/HOST/PORT in .env)
    .venv/bin/python -m github_mcp.server --transport streamable-http

This module only does wiring — no business logic, no SQLAlchemy import.
"""

from __future__ import annotations

import argparse
import logging
from typing import Literal

from devbrain_common.approval_tools import register_approval_tools
from mcp.server.fastmcp import FastMCP

from github_mcp.auth import require_min_role
from github_mcp.config import get_github_mcp_settings
from github_mcp.repositories.unit_of_work import unit_of_work
from github_mcp.tools import github_tools

logger = logging.getLogger("github_mcp")


def create_server() -> FastMCP:
    settings = get_github_mcp_settings()
    mcp = FastMCP(
        name="devbrain-github-mcp",
        instructions=(
            "DevBrain GitHub MCP: search/get issues, list/get pull requests, "
            "search commits, and fetch repository activity. Backed by "
            "synthetic (fake) GitHub data in Postgres today — every tool "
            "is low risk and read-only. See DevBrain_vision.md §11.4/§24 for "
            "the planned real-GitHub-API swap. request_approval/"
            "list_pending_approvals/decide_approval (for reviewing other "
            "services' pending write approvals) are also available here."
        ),
        host=settings.github_mcp_host,
        port=settings.github_mcp_port,
    )

    github_tools.register(mcp)
    register_approval_tools(mcp, unit_of_work=unit_of_work, require_min_role=require_min_role)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="DevBrain GitHub MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=None,
        help="Defaults to GITHUB_MCP_TRANSPORT env var, then 'stdio'.",
    )
    args = parser.parse_args()

    settings = get_github_mcp_settings()
    transport: Literal["stdio", "sse", "streamable-http"] = (
        args.transport or settings.github_mcp_transport  # type: ignore[assignment]
    )

    logging.basicConfig(level=logging.INFO)
    logger.info("starting github-mcp", extra={"transport": transport})

    mcp = create_server()
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
