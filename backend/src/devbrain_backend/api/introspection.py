"""Shared introspection helpers behind `GET /tools`, `GET /permissions`, and
`GET /activity`'s `server` field — every fact these endpoints expose is
derived from the five services' own `create_server()` + `risk.py`, never a
hand-copied duplicate table (per this phase's own brief).

**`create_server()` + `list_tools()`** is the exact same real FastMCP
registration path each service's own `test_*_server_wiring.py` exercises
(Phase 6) — calling it here proves the tool list is what the servers
*actually* register, not a static guess.

**Risk tiers** come from each service's own `risk.py`
(`devbrain_common.risk.make_risk_lookup`-backed) — as of the Phase 6
gap-fix addendum (see PROGRESS_REPORT.md), `knowledge_mcp` has a real
`risk.py` too (added to close its approval-gate gap), so all five services
are now treated uniformly here; no per-service fallback/exception is
needed.

**`min_role` per tool** is *not* stored anywhere as data — every
`tools/*.py` function calls `require_min_role(ctx, Role.X)` as its first
line, imperatively, and that call is the only source of truth. Across all
five services, `low` <-> `Role.VIEWER`, `medium` <-> `Role.USER`, `high` <->
`Role.ADMIN` holds with zero exceptions (verified via
`grep -rn "require_min_role(ctx, Role\\." services/*/src/*/tools/*.py` —
every read tool calls `Role.VIEWER`, every medium-risk write calls
`Role.USER`, and `knowledge_mcp`'s one high-risk tool, `notes.delete`,
calls `Role.ADMIN`), so `min_role` is derived from `risk_tier` for every
service, including Knowledge MCP.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import calendar_mcp.risk as _calendar_risk
import github_mcp.risk as _github_risk
import knowledge_mcp.risk as _knowledge_risk
import project_mcp.risk as _project_risk
import task_mcp.risk as _task_risk
from calendar_mcp.server import create_server as _create_calendar_server
from devbrain_common.auth import Role
from devbrain_common.risk import RiskTier
from github_mcp.server import create_server as _create_github_server
from knowledge_mcp.server import create_server as _create_knowledge_server
from project_mcp.server import create_server as _create_project_server
from task_mcp.server import create_server as _create_task_server

# Registered identically on all five servers by
# `devbrain_common.approval_tools.register_approval_tools` — "owning
# server" is ambiguous for these three, so `/activity` reports them under
# the synthetic "shared" pseudo-server instead of picking one arbitrarily.
# Role requirements below are copied straight from
# `packages/common/src/devbrain_common/approval_tools.py`'s own
# `require_min_role(ctx, Role.X)` calls (the one shared module every server
# mounts), not reinvented.
SHARED_APPROVAL_TOOL_MIN_ROLES: dict[str, Role] = {
    "request_approval": Role.USER,
    "list_pending_approvals": Role.USER,
    "decide_approval": Role.ADMIN,
}
SHARED_APPROVAL_TOOL_NAMES = frozenset(SHARED_APPROVAL_TOOL_MIN_ROLES)

_SERVER_FACTORIES: dict[str, Callable[[], Any]] = {
    "knowledge-mcp": _create_knowledge_server,
    "project-mcp": _create_project_server,
    "task-mcp": _create_task_server,
    "github-mcp": _create_github_server,
    "calendar-mcp": _create_calendar_server,
}

RiskLookup = tuple[Callable[[str], RiskTier], Callable[[str], bool]]

_RISK_LOOKUPS: dict[str, RiskLookup] = {
    "knowledge-mcp": (_knowledge_risk.risk_tier_for, _knowledge_risk.approval_required),
    "project-mcp": (_project_risk.risk_tier_for, _project_risk.approval_required),
    "task-mcp": (_task_risk.risk_tier_for, _task_risk.approval_required),
    "github-mcp": (_github_risk.risk_tier_for, _github_risk.approval_required),
    "calendar-mcp": (_calendar_risk.risk_tier_for, _calendar_risk.approval_required),
}

# risk_tier -> min_role holds uniformly across all five services (verified
# via `require_min_role(ctx, Role.X)` grep, see module docstring).
_MIN_ROLE_BY_RISK_TIER: dict[RiskTier, Role] = {
    RiskTier.LOW: Role.VIEWER,
    RiskTier.MEDIUM: Role.USER,
    RiskTier.HIGH: Role.ADMIN,
}


async def list_server_tools() -> dict[str, list[str]]:
    """`{server_name: [tool_name, ...]}` for all five servers, sorted, via
    a real `create_server()` + `await mcp.list_tools()` call each — no
    network, no DB (`create_server()` only wires tool registrations)."""
    result: dict[str, list[str]] = {}
    for name, factory in _SERVER_FACTORIES.items():
        mcp = factory()
        tools = await mcp.list_tools()
        result[name] = sorted(t.name for t in tools)
    return result


def tool_owner_map(server_tools: dict[str, list[str]]) -> dict[str, str]:
    """`tool_name -> owning server`, skipping the shared approval tool
    names (see `SHARED_APPROVAL_TOOL_NAMES` — identical across all five, so
    "owner" is ambiguous; `/activity` reports those as `server="shared"`
    instead of consulting this map)."""
    owner: dict[str, str] = {}
    for server, tools in server_tools.items():
        for tool in tools:
            if tool in SHARED_APPROVAL_TOOL_NAMES:
                continue
            owner[tool] = server
    return owner


def permissions_for_tool(server: str, tool_name: str) -> dict[str, Any]:
    """One `/permissions` row: `{tool, risk_tier, min_role, approval_required}`.

    See module docstring for exactly how `min_role` is derived vs. stated.
    """
    if tool_name in SHARED_APPROVAL_TOOL_NAMES:
        min_role = SHARED_APPROVAL_TOOL_MIN_ROLES[tool_name]
        # `decide_approval` actually changes an approval's disposition
        # (admin-only, per its own role requirement above) — everything
        # else here is a read or a request that doesn't itself mutate
        # business data, so only `decide_approval` is tagged medium.
        risk_tier = RiskTier.MEDIUM if tool_name == "decide_approval" else RiskTier.LOW
        return {
            "tool": tool_name,
            "risk_tier": risk_tier.value,
            "min_role": min_role.value,
            "approval_required": False,
        }

    risk_tier_for, approval_required = _RISK_LOOKUPS[server]
    risk_tier = risk_tier_for(tool_name)
    min_role = _MIN_ROLE_BY_RISK_TIER[risk_tier]

    return {
        "tool": tool_name,
        "risk_tier": risk_tier.value,
        "min_role": min_role.value,
        "approval_required": approval_required(tool_name),
    }


__all__ = [
    "SHARED_APPROVAL_TOOL_MIN_ROLES",
    "SHARED_APPROVAL_TOOL_NAMES",
    "list_server_tools",
    "permissions_for_tool",
    "tool_owner_map",
]
