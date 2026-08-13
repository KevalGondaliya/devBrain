"""Tool-entry auth: resolve the calling actor's role and enforce it.

Phase 6 consolidation: thin per-service adapter over
`devbrain_common.mcp_auth`, which now holds the actual resolution/role/
rate-limit logic this module originated in Phase 3 (every sibling service
copied it verbatim in Phases 4-5) — see PROGRESS_REPORT.md Phase 6
"Decisions made". `resolve_actor`/`require_min_role` below are bound once
at import time to this service's own `KNOWLEDGE_MCP_STDIO_ROLE` env var and
`KnowledgeMCPSettings`.
"""

from __future__ import annotations

from devbrain_common.mcp_auth import (
    STDIO_ACTOR_LABEL,
    ActorContext,
    ActorResolver,
    RequireMinRole,
    build_actor_resolver,
    make_require_min_role,
)

from knowledge_mcp.config import get_knowledge_mcp_settings

__all__ = ["STDIO_ACTOR_LABEL", "ActorContext", "require_min_role", "resolve_actor"]

resolve_actor: ActorResolver = build_actor_resolver(
    stdio_role_env_var="KNOWLEDGE_MCP_STDIO_ROLE",
    stdio_role_default=lambda: get_knowledge_mcp_settings().knowledge_mcp_stdio_role,
)

require_min_role: RequireMinRole = make_require_min_role(resolve_actor)
