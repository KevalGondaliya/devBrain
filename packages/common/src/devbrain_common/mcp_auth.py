"""Shared MCP tool-entry auth: resolve the calling actor's role from an MCP
`Context` and enforce it — the logic every service's `auth.py` reinvented
identically (down to the docstrings) in Phases 3-5, save for which env var
name/settings object backs its stdio-role default.

Each service keeps a thin `auth.py` that binds `build_actor_resolver(...)`
to its own `<SERVICE>_MCP_STDIO_ROLE` env var name and settings accessor,
then wraps the result with `make_require_min_role(...)`. See
`services/task_mcp/src/task_mcp/auth.py` for the reference shape every
other service's `auth.py` now mirrors.

Auth wired at the tool-function level, not via `devbrain_common.auth`'s
`require_role` decorator verbatim: that decorator expects the wrapped
function to be *called* with a `role=` kwarg, which would have to be part
of the tool's client-visible schema (letting a malicious client just pass
whatever role it wants). Instead every `@mcp.tool()` function calls
`require_min_role(ctx, Role.X)` as its first line, using the MCP `Context`
parameter FastMCP auto-injects and excludes from the client-visible schema.

Rate limiting (DevBrain_vision.md §15/§22) lives in `make_require_min_role`
rather than in `devbrain_common.mcp_tooling.handle_tool_errors`: it's
actor-keyed, and the actor only becomes known once `resolve_actor` runs —
`require_min_role` is the one call every tool makes as its very first line
specifically to resolve that actor, so enforcing the limit there (a) avoids
resolving the actor a second time inside a generic decorator that would
otherwise have to sniff a `ctx` kwarg out of `*args/**kwargs`, and (b)
still gates *every* write and read tool identically, since every tool body
calls `require_min_role` unconditionally before doing anything else.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from devbrain_common.auth import Role, TokenStore, check_role
from devbrain_common.config import get_settings
from devbrain_common.errors import UnauthorizedError
from devbrain_common.ratelimit import get_rate_limiter

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

# Actor label used for audit logs / logging when running over stdio, where
# there is no per-request bearer token to identify the caller.
STDIO_ACTOR_LABEL = "stdio-local-dev"


@dataclass(frozen=True)
class ActorContext:
    """The resolved identity of whoever is calling a tool right now."""

    role: Role
    actor: str  # human-readable label for audit_logs.actor — never a raw token


ActorResolver = Callable[["Context[Any, Any, Any] | None"], ActorContext]
RequireMinRole = Callable[["Context[Any, Any, Any] | None", Role], ActorContext]


def _token_store() -> TokenStore:
    return TokenStore.from_env_value(get_settings().mcp_api_tokens)


def _http_request(ctx: Context[Any, Any, Any] | None) -> Any | None:
    """Best-effort extraction of the raw HTTP request from a tool `Context`.

    Returns `None` for stdio transport (no HTTP request in scope) or when
    `ctx` itself is `None` (e.g. a unit test calling a tool function
    directly without going through FastMCP).
    """
    if ctx is None:
        return None
    try:
        request_context = ctx.request_context
    except ValueError:
        return None
    request = getattr(request_context, "request", None)
    if request is None or not hasattr(request, "headers"):
        return None
    return request


def build_actor_resolver(
    *,
    stdio_role_env_var: str,
    stdio_role_default: Callable[[], str],
) -> ActorResolver:
    """Build a `resolve_actor(ctx)` function bound to one service's own
    stdio-role env var name and settings default.

    `stdio_role_default` is a zero-arg callable (not a plain string) so it's
    read lazily — each service passes something like
    `lambda: get_task_mcp_settings().task_mcp_stdio_role`, keeping this
    module free of any per-service settings import.

    - HTTP/SSE transport: reads `Authorization: Bearer <token>` off the raw
      ASGI request and resolves it via `MCP_API_TOKENS`
      (`devbrain_common.auth.TokenStore`). Missing/malformed header or
      unrecognized token -> `UnauthorizedError`.
    - stdio transport (no HTTP request reachable from `ctx`): auth is
      skipped per the plan's local-dev carve-out; role defaults to
      `stdio_role_env_var`'s value (falling back to `stdio_role_default()`),
      actor label is the fixed `STDIO_ACTOR_LABEL`.
    """

    def resolve_actor(ctx: Context[Any, Any, Any] | None) -> ActorContext:
        request = _http_request(ctx)
        if request is None:
            # `os.environ.get(key, stdio_role_default())` looks lazy but
            # isn't -- Python evaluates a positional default argument
            # eagerly, so `stdio_role_default()` (and, transitively, each
            # service's `lru_cache`d `get_<service>_mcp_settings()`) would
            # run on *every* stdio call, not just when the env var is
            # actually absent. That matters beyond performance: the first
            # such call permanently caches whatever `PROJECT_MCP_STDIO_ROLE`
            # (etc.) happens to be set to at that moment as the "default" for
            # the rest of the process -- a real bug this module's own
            # docstring already claimed didn't exist ("read lazily"). Fixed
            # by only calling `stdio_role_default()` when actually needed.
            role_str = os.environ.get(stdio_role_env_var)
            if role_str is None:
                role_str = stdio_role_default()
            try:
                role = Role(role_str)
            except ValueError:
                role = Role.ADMIN
            return ActorContext(role=role, actor=STDIO_ACTOR_LABEL)

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise UnauthorizedError("Missing 'Authorization: Bearer <token>' header.")
        token = header[len("bearer ") :].strip()
        if not token:
            raise UnauthorizedError("Empty bearer token.")
        role = _token_store().authenticate(token)
        # Never log/store the raw token (ORCHESTRATION.md: "never log
        # secrets or full auth tokens") — a short non-reversible-looking
        # prefix is enough to distinguish actors in the audit log without
        # exposing the secret.
        actor = f"token:{token[:4]}***"
        return ActorContext(role=role, actor=actor)

    return resolve_actor


def make_require_min_role(resolve_actor: ActorResolver) -> RequireMinRole:
    """Build a `require_min_role(ctx, min_role)` bound to `resolve_actor`.

    Resolves the caller's actor context, enforces the minimum role, then
    enforces the process-wide rate limit (`devbrain_common.ratelimit
    .get_rate_limiter()`, keyed by actor) — see module docstring for why
    the rate limit lives here. Raises `UnauthorizedError` (no/invalid
    credentials), `ForbiddenError` (insufficient role), or `RateLimitedError`
    (actor over budget) — all structured `DevBrainError` subclasses, never a
    raw exception.
    """

    def require_min_role(ctx: Context[Any, Any, Any] | None, min_role: Role) -> ActorContext:
        actor_ctx = resolve_actor(ctx)
        check_role(actor_ctx.role, min_role)
        get_rate_limiter().check(actor_ctx.actor)
        return actor_ctx

    return require_min_role
