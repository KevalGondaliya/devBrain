"""Calendar MCP — FastMCP entrypoint.

Wires config + tools. Runnable two ways:

    # stdio (local Claude Desktop/Code dev connection; no bearer auth)
    .venv/bin/python -m calendar_mcp.server
    .venv/bin/python -m calendar_mcp.server --transport stdio

    # HTTP (bearer auth enforced per-tool via calendar_mcp.auth; see
    # CALENDAR_MCP_TRANSPORT/HOST/PORT in .env)
    .venv/bin/python -m calendar_mcp.server --transport streamable-http

This module only does wiring — no business logic, no SQLAlchemy import.
"""

from __future__ import annotations

import argparse
import logging
from typing import Literal

from devbrain_common.approval_tools import register_approval_tools
from mcp.server.fastmcp import FastMCP

from calendar_mcp.auth import require_min_role
from calendar_mcp.config import get_calendar_mcp_settings
from calendar_mcp.repositories.unit_of_work import unit_of_work
from calendar_mcp.tools import calendar_tools

logger = logging.getLogger("calendar_mcp")


def create_server() -> FastMCP:
    settings = get_calendar_mcp_settings()
    mcp = FastMCP(
        name="devbrain-calendar-mcp",
        instructions=(
            "DevBrain Calendar MCP: today's events, this week's events, "
            "keyword search over events, and creating a new event. "
            "`create_event` is a medium-risk write — Role.USER callers need an "
            "approval_id from request_approval first (Role.ADMIN may bypass), and "
            "it accepts an idempotency_key to make retries safe. Backed by "
            "synthetic (fake) calendar data in Postgres today; see "
            "DevBrain_vision.md §11.5/§24 for the planned real-provider (Google "
            "Calendar) swap. request_approval/list_pending_approvals/"
            "decide_approval are also available here."
        ),
        host=settings.calendar_mcp_host,
        port=settings.calendar_mcp_port,
    )

    calendar_tools.register(mcp)
    register_approval_tools(mcp, unit_of_work=unit_of_work, require_min_role=require_min_role)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="DevBrain Calendar MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=None,
        help="Defaults to CALENDAR_MCP_TRANSPORT env var, then 'stdio'.",
    )
    args = parser.parse_args()

    settings = get_calendar_mcp_settings()
    transport: Literal["stdio", "sse", "streamable-http"] = (
        args.transport or settings.calendar_mcp_transport  # type: ignore[assignment]
    )

    logging.basicConfig(level=logging.INFO)
    logger.info("starting calendar-mcp", extra={"transport": transport})

    mcp = create_server()
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
