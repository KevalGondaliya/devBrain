"""Re-exports the shared tool-wrapper helpers (Phase 6 consolidation).

`handle_tool_errors`/`dto_to_dict` had zero service-specific behavior across
all five MCP servers — see PROGRESS_REPORT.md Phase 6 "Decisions made" —
so the real implementation now lives once in `devbrain_common.mcp_tooling`.
This module is kept as a one-line re-export so `tools/*.py`'s existing
`from calendar_mcp.tools._common import ...` imports (and this service's own
`test_calendar_mcp_tools_common.py`) don't need to change.
"""

from __future__ import annotations

from devbrain_common.mcp_tooling import dto_to_dict, handle_tool_errors

__all__ = ["dto_to_dict", "handle_tool_errors"]
