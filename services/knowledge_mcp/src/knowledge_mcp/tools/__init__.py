"""Thin FastMCP `@mcp.tool()` functions.

Every tool in this package follows the same shape:
    1. type-hint/`Annotated[..., Field(...)]` args -> FastMCP validates them
       as a Pydantic model before the function body ever runs.
    2. `knowledge_mcp.auth.require_min_role(ctx, Role.X)` — resolves the
       caller's role from the MCP request context and raises if
       insufficient. Read tools require `Role.VIEWER`; writes require
       `Role.USER` (per this phase's task brief).
    3. exactly one call into `knowledge_mcp.services.*` — no SQLAlchemy
       import anywhere in this directory.
    4. `knowledge_mcp.tools._common.handle_tool_errors` on every function so
       only structured `{"error": {"code", "message"}}` envelopes ever
       reach the client, never a raw traceback.
"""

from __future__ import annotations
