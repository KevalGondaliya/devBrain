"""`GET /tools` — which of the five MCP servers exist and what tools each
one registers, for Phase 9's Tools page (DevBrain_vision.md §20's "Show
connected MCP servers and available tools"). Introspected via each
server's real `create_server()` + `list_tools()`
(`devbrain_backend.api.introspection.list_server_tools`), not a static
hand-maintained list.
"""

from __future__ import annotations

from devbrain_common.auth import Role
from devbrain_common.mcp_auth import ActorContext
from fastapi import APIRouter, Depends

from devbrain_backend.api.auth import require_role
from devbrain_backend.api.introspection import list_server_tools
from devbrain_backend.api.schemas import ServerTools, ToolsResponse

router = APIRouter(tags=["tools"])

# Module-level singleton, evaluated once at import time — see
# `permissions_router.py`'s identical comment for why (ruff B008).
_require_viewer = Depends(require_role(Role.VIEWER))


@router.get("/tools", response_model=ToolsResponse)
async def get_tools(_actor_ctx: ActorContext = _require_viewer) -> ToolsResponse:
    server_tools = await list_server_tools()
    return ToolsResponse(
        servers=[ServerTools(server=server, tools=tools) for server, tools in server_tools.items()]
    )
