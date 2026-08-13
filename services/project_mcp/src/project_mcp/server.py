"""Project MCP — FastMCP entrypoint.

Wires config + tools. Runnable two ways:

    # stdio (local Claude Desktop/Code dev connection; no bearer auth)
    .venv/bin/python -m project_mcp.server
    .venv/bin/python -m project_mcp.server --transport stdio

    # HTTP (bearer auth enforced per-tool via project_mcp.auth; see
    # PROJECT_MCP_TRANSPORT/HOST/PORT in .env)
    .venv/bin/python -m project_mcp.server --transport streamable-http

This module only does wiring — no business logic, no SQLAlchemy import.
"""

from __future__ import annotations

import argparse
import logging
from typing import Literal

from devbrain_common.approval_tools import register_approval_tools
from mcp.server.fastmcp import FastMCP

from project_mcp.auth import require_min_role
from project_mcp.config import get_project_mcp_settings
from project_mcp.repositories.unit_of_work import unit_of_work
from project_mcp.tools import projects_tools

logger = logging.getLogger("project_mcp")


def create_server() -> FastMCP:
    settings = get_project_mcp_settings()
    mcp = FastMCP(
        name="devbrain-project-mcp",
        instructions=(
            "DevBrain Project MCP: list/search/get projects, read and update "
            "project status. `update_project_status` is a medium-risk write — "
            "Role.USER callers need an approval_id from request_approval first "
            "(Role.ADMIN may bypass). request_approval/list_pending_approvals/"
            "decide_approval are also available here."
        ),
        host=settings.project_mcp_host,
        port=settings.project_mcp_port,
    )

    projects_tools.register(mcp)
    register_approval_tools(mcp, unit_of_work=unit_of_work, require_min_role=require_min_role)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="DevBrain Project MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=None,
        help="Defaults to PROJECT_MCP_TRANSPORT env var, then 'stdio'.",
    )
    args = parser.parse_args()

    settings = get_project_mcp_settings()
    transport: Literal["stdio", "sse", "streamable-http"] = (
        args.transport or settings.project_mcp_transport  # type: ignore[assignment]
    )

    logging.basicConfig(level=logging.INFO)
    logger.info("starting project-mcp", extra={"transport": transport})

    mcp = create_server()
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
