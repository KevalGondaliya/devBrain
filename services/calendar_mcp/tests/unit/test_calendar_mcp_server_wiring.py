"""`create_server()` must actually construct without FastMCP choking on tool
schemas — see `services/project_mcp/tests/unit/test_server_wiring.py` for
the real bug this catches (PROGRESS_REPORT.md Phase 6 "Decisions made").
"""

from __future__ import annotations

from calendar_mcp.server import create_server


async def test_create_server_registers_tools_without_error() -> None:
    mcp = create_server()
    tools = await mcp.list_tools()
    names = {t.name for t in tools}

    assert {"get_today_events", "get_week_events", "find_event", "create_event"} <= names
    assert {"request_approval", "list_pending_approvals", "decide_approval"} <= names
