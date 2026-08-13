"""`create_server()` must actually construct without FastMCP choking on tool
schemas (Phase 6 caught a real bug here: a `TYPE_CHECKING`-only `Context`/
`FastMCP` import in `devbrain_common.approval_tools` passed every unit test
and mypy but broke `@mcp.tool()`'s runtime annotation introspection the
first time a server actually started — see PROGRESS_REPORT.md Phase 6
"Decisions made"). This test is the regression net: no DB, no network,
just proves registration itself succeeds and the shared approval tools are
mounted alongside this service's own tools.
"""

from __future__ import annotations

from project_mcp.server import create_server


async def test_create_server_registers_tools_without_error() -> None:
    mcp = create_server()
    tools = await mcp.list_tools()
    names = {t.name for t in tools}

    assert {"list_projects", "get_project", "update_project_status"} <= names
    assert {"request_approval", "list_pending_approvals", "decide_approval"} <= names
