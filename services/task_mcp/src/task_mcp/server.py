"""Task MCP — FastMCP entrypoint.

Wires config + tools. Runnable two ways:

    # stdio (local Claude Desktop/Code dev connection; no bearer auth)
    .venv/bin/python -m task_mcp.server
    .venv/bin/python -m task_mcp.server --transport stdio

    # HTTP (bearer auth enforced per-tool via task_mcp.auth; see
    # TASK_MCP_TRANSPORT/HOST/PORT in .env)
    .venv/bin/python -m task_mcp.server --transport streamable-http

This module only does wiring — no business logic, no SQLAlchemy import.
"""

from __future__ import annotations

import argparse
import logging
from typing import Literal

from devbrain_common.approval_tools import register_approval_tools
from mcp.server.fastmcp import FastMCP

from task_mcp.auth import require_min_role
from task_mcp.config import get_task_mcp_settings
from task_mcp.repositories.unit_of_work import unit_of_work
from task_mcp.tools import tasks_tools

logger = logging.getLogger("task_mcp")


def create_server() -> FastMCP:
    settings = get_task_mcp_settings()
    mcp = FastMCP(
        name="devbrain-task-mcp",
        instructions=(
            "DevBrain Task MCP: list/search/get tasks, create/update/complete "
            "tasks under a project. `create_task`/`update_task`/`complete_task` "
            "are medium-risk writes — Role.USER callers need an approval_id from "
            "request_approval first (Role.ADMIN may bypass). `create_task` also "
            "accepts an idempotency_key to make retries safe. request_approval/"
            "list_pending_approvals/decide_approval are also available here."
        ),
        host=settings.task_mcp_host,
        port=settings.task_mcp_port,
    )

    tasks_tools.register(mcp)
    register_approval_tools(mcp, unit_of_work=unit_of_work, require_min_role=require_min_role)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="DevBrain Task MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=None,
        help="Defaults to TASK_MCP_TRANSPORT env var, then 'stdio'.",
    )
    args = parser.parse_args()

    settings = get_task_mcp_settings()
    transport: Literal["stdio", "sse", "streamable-http"] = (
        args.transport or settings.task_mcp_transport  # type: ignore[assignment]
    )

    logging.basicConfig(level=logging.INFO)
    logger.info("starting task-mcp", extra={"transport": transport})

    mcp = create_server()
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
