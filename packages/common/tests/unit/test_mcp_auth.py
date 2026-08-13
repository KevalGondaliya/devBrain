"""`devbrain_common.mcp_auth` — shared actor resolution + role/rate-limit
enforcement every service's thin `auth.py` now binds itself to.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from devbrain_common import mcp_auth
from devbrain_common.auth import Role
from devbrain_common.errors import ForbiddenError, RateLimitedError, UnauthorizedError
from devbrain_common.ratelimit import RateLimiter


@dataclass
class FakeHeaders:
    values: dict[str, str]

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key.lower(), default)


@dataclass
class FakeRequest:
    headers: FakeHeaders


class FakeRequestContext:
    def __init__(self, request: FakeRequest | None) -> None:
        self.request = request


class FakeContext:
    def __init__(self, request: FakeRequest | None) -> None:
        self._request_context = FakeRequestContext(request)

    @property
    def request_context(self) -> FakeRequestContext:
        return self._request_context


class RaisingContext:
    """Mimics a real `Context` constructed with no request in scope (stdio)."""

    @property
    def request_context(self) -> FakeRequestContext:
        raise ValueError("Context is not available outside of a request")


def _resolver(default_role: str = "admin") -> mcp_auth.ActorResolver:
    return mcp_auth.build_actor_resolver(
        stdio_role_env_var="TEST_MCP_STDIO_ROLE",
        stdio_role_default=lambda: default_role,
    )


def test_resolve_actor_stdio_uses_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_MCP_STDIO_ROLE", raising=False)
    resolve_actor = _resolver("admin")
    actor_ctx = resolve_actor(None)
    assert actor_ctx.role == Role.ADMIN
    assert actor_ctx.actor == mcp_auth.STDIO_ACTOR_LABEL


def test_resolve_actor_stdio_honors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_MCP_STDIO_ROLE", "viewer")
    resolve_actor = _resolver("admin")
    actor_ctx = resolve_actor(None)
    assert actor_ctx.role == Role.VIEWER


def test_resolve_actor_context_without_request_context_treated_as_stdio() -> None:
    resolve_actor = _resolver("user")
    actor_ctx = resolve_actor(RaisingContext())  # type: ignore[arg-type]
    assert actor_ctx.role == Role.USER
    assert actor_ctx.actor == mcp_auth.STDIO_ACTOR_LABEL


def test_resolve_actor_http_valid_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_auth, "get_settings", lambda: type("S", (), {"mcp_api_tokens": "sekret:admin"})()
    )
    resolve_actor = _resolver()
    ctx = FakeContext(FakeRequest(FakeHeaders({"authorization": "Bearer sekret"})))
    actor_ctx = resolve_actor(ctx)  # type: ignore[arg-type]
    assert actor_ctx.role == Role.ADMIN
    assert "sekret" not in actor_ctx.actor


def test_resolve_actor_http_missing_header_raises() -> None:
    resolve_actor = _resolver()
    ctx = FakeContext(FakeRequest(FakeHeaders({})))
    with pytest.raises(UnauthorizedError):
        resolve_actor(ctx)  # type: ignore[arg-type]


def test_resolve_actor_http_unknown_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_auth, "get_settings", lambda: type("S", (), {"mcp_api_tokens": "sekret:admin"})()
    )
    resolve_actor = _resolver()
    ctx = FakeContext(FakeRequest(FakeHeaders({"authorization": "Bearer wrong-token"})))
    with pytest.raises(UnauthorizedError):
        resolve_actor(ctx)  # type: ignore[arg-type]


def test_require_min_role_raises_forbidden_when_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_MCP_STDIO_ROLE", "viewer")
    require_min_role = mcp_auth.make_require_min_role(_resolver())
    with pytest.raises(ForbiddenError):
        require_min_role(None, Role.ADMIN)


def test_require_min_role_passes_when_sufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_MCP_STDIO_ROLE", "admin")
    require_min_role = mcp_auth.make_require_min_role(_resolver())
    actor_ctx = require_min_role(None, Role.USER)
    assert actor_ctx.role == Role.ADMIN


def test_require_min_role_enforces_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 6: rate limiting is keyed by actor and enforced right where the
    actor becomes known — `require_min_role`. Injects a tiny limiter (no
    real sleeping) via the module-level `get_rate_limiter` seam."""
    tiny_limiter = RateLimiter(rate_per_minute=1)
    monkeypatch.setattr(mcp_auth, "get_rate_limiter", lambda: tiny_limiter)
    monkeypatch.setenv("TEST_MCP_STDIO_ROLE", "admin")
    require_min_role = mcp_auth.make_require_min_role(_resolver())

    require_min_role(None, Role.VIEWER)  # consumes the one token, should not raise
    with pytest.raises(RateLimitedError):
        require_min_role(None, Role.VIEWER)


def test_require_min_role_rate_limit_is_per_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    tiny_limiter = RateLimiter(rate_per_minute=1)
    monkeypatch.setattr(mcp_auth, "get_rate_limiter", lambda: tiny_limiter)
    monkeypatch.setenv("TEST_MCP_STDIO_ROLE", "admin")
    require_min_role = mcp_auth.make_require_min_role(_resolver())

    ctx_a = FakeContext(FakeRequest(FakeHeaders({"authorization": "Bearer sekret"})))
    monkeypatch.setattr(
        mcp_auth, "get_settings", lambda: type("S", (), {"mcp_api_tokens": "sekret:viewer"})()
    )
    require_min_role(ctx_a, Role.VIEWER)  # type: ignore[arg-type]
    # A different actor (stdio, distinct label) still has a fresh bucket.
    require_min_role(None, Role.VIEWER)
