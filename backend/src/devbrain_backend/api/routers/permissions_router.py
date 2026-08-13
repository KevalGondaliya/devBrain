"""`GET /permissions` — role -> tool -> risk-tier matrix, per service, for
Phase 9's Permissions page (DevBrain_vision.md §20's "Show role/tool
permissions"). Built from `devbrain_backend.api.introspection`, which
sources every field from the services' own `create_server()`/`risk.py` —
see that module's docstring for exactly what's introspected vs. derived.
"""

from __future__ import annotations

from devbrain_common.auth import Role
from devbrain_common.mcp_auth import ActorContext
from fastapi import APIRouter, Depends

from devbrain_backend.api.auth import require_role
from devbrain_backend.api.introspection import list_server_tools, permissions_for_tool
from devbrain_backend.api.schemas import PermissionsResponse, ServerPermissions, ToolPermission

router = APIRouter(tags=["permissions"])

# Module-level singleton (not built inline in the route signature) so ruff's
# B008 doesn't read `require_role(Role.VIEWER)` as a fresh call happening on
# every request — it's evaluated once, at import time, same as every other
# router in this package.
_require_viewer = Depends(require_role(Role.VIEWER))


@router.get("/permissions", response_model=PermissionsResponse)
async def get_permissions(_actor_ctx: ActorContext = _require_viewer) -> PermissionsResponse:
    server_tools = await list_server_tools()
    servers = {
        server: ServerPermissions(
            tools=[ToolPermission(**permissions_for_tool(server, tool)) for tool in tools]
        )
        for server, tools in server_tools.items()
    }
    return PermissionsResponse(roles=[role.value for role in Role], servers=servers)
