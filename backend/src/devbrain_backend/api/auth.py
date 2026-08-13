"""FastAPI auth: resolves the caller's role from an `Authorization: Bearer
<token>` header against the same `MCP_API_TOKENS` token store every MCP
tool already authenticates against (`devbrain_common.auth.TokenStore`), and
enforces a minimum role via `devbrain_common.auth.check_role` — the exact
primitives `devbrain_common.mcp_auth.build_actor_resolver`/
`make_require_min_role` also wrap, just for MCP's `Context` object instead
of a FastAPI `Request`.

Deliberately *not* calling `mcp_auth.build_actor_resolver` verbatim: that
function is built to pull the raw ASGI request out of an MCP `Context`
(`ctx.request_context.request`), which doesn't exist in a FastAPI handler —
a FastAPI `Request` already *is* that raw request, one layer up. The
bearer-token-extraction glue below is intentionally the same few lines
`build_actor_resolver`'s closure has (header parsing, `token:xxxx***` actor
label, never logging the raw token), adapted to Starlette's
`Request.headers`; every actual authentication decision — token lookup,
role check, rate limit — is the same `devbrain_common` call every MCP tool
makes, not reimplemented.
"""

from __future__ import annotations

from collections.abc import Callable

from devbrain_common.auth import Role, TokenStore, check_role
from devbrain_common.config import get_settings
from devbrain_common.errors import UnauthorizedError
from devbrain_common.mcp_auth import ActorContext
from devbrain_common.ratelimit import get_rate_limiter
from fastapi import Request


def _token_store() -> TokenStore:
    return TokenStore.from_env_value(get_settings().mcp_api_tokens)


def resolve_actor(request: Request) -> ActorContext:
    """Resolve the calling actor's `Role` from `request`'s bearer token.

    Raises `UnauthorizedError` (-> 401, via `main.py`'s global
    `DevBrainError` handler) for a missing/malformed header, empty token, or
    a token not present in `MCP_API_TOKENS`.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise UnauthorizedError("Missing 'Authorization: Bearer <token>' header.")
    token = header[len("bearer ") :].strip()
    if not token:
        raise UnauthorizedError("Empty bearer token.")
    role = _token_store().authenticate(token)
    # Never log/store the raw token (ORCHESTRATION.md §1) — same short
    # non-reversible-looking prefix convention as `devbrain_common.mcp_auth`.
    actor = f"token:{token[:4]}***"
    return ActorContext(role=role, actor=actor)


def require_role(min_role: Role) -> Callable[[Request], ActorContext]:
    """FastAPI dependency factory — mirrors
    `devbrain_common.mcp_auth.make_require_min_role` exactly (resolve actor,
    enforce minimum role, enforce the actor-keyed process-wide rate limit),
    sourced from a FastAPI `Request` instead of an MCP `Context`. Every
    router in `devbrain_backend.api.routers` depends on this, so every HTTP
    endpoint enforces the same role/rate-limit checks the MCP tools do.
    """

    def _dependency(request: Request) -> ActorContext:
        actor_ctx = resolve_actor(request)
        check_role(actor_ctx.role, min_role)
        get_rate_limiter().check(actor_ctx.actor)
        return actor_ctx

    return _dependency
