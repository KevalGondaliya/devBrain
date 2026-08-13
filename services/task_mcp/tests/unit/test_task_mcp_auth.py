"""`task_mcp.auth` — role resolution + enforcement at the tool boundary."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from devbrain_common import mcp_auth
from devbrain_common.auth import Role
from devbrain_common.errors import ForbiddenError, UnauthorizedError

from task_mcp import auth as tmcp_auth


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
    """Mimics a real `Context` constructed with no request in scope (stdio),
    where accessing `.request_context` itself raises."""

    @property
    def request_context(self) -> FakeRequestContext:
        raise ValueError("Context is not available outside of a request")


def test_resolve_actor_stdio_defaults_to_configured_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TASK_MCP_STDIO_ROLE", raising=False)
    actor_ctx = tmcp_auth.resolve_actor(None)
    assert actor_ctx.role == Role.ADMIN  # default per TaskMCPSettings
    assert actor_ctx.actor == tmcp_auth.STDIO_ACTOR_LABEL


def test_resolve_actor_stdio_honors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASK_MCP_STDIO_ROLE", "viewer")
    actor_ctx = tmcp_auth.resolve_actor(None)
    assert actor_ctx.role == Role.VIEWER


def test_resolve_actor_context_without_request_context_treated_as_stdio() -> None:
    actor_ctx = tmcp_auth.resolve_actor(RaisingContext())  # type: ignore[arg-type]
    assert actor_ctx.actor == tmcp_auth.STDIO_ACTOR_LABEL


def test_resolve_actor_http_valid_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_auth, "get_settings", lambda: type("S", (), {"mcp_api_tokens": "sekret:admin"})()
    )
    ctx = FakeContext(FakeRequest(FakeHeaders({"authorization": "Bearer sekret"})))
    actor_ctx = tmcp_auth.resolve_actor(ctx)  # type: ignore[arg-type]
    assert actor_ctx.role == Role.ADMIN
    assert "sekret" not in actor_ctx.actor  # never logs the raw token


def test_resolve_actor_http_missing_header_raises() -> None:
    ctx = FakeContext(FakeRequest(FakeHeaders({})))
    with pytest.raises(UnauthorizedError):
        tmcp_auth.resolve_actor(ctx)  # type: ignore[arg-type]


def test_resolve_actor_http_unknown_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_auth, "get_settings", lambda: type("S", (), {"mcp_api_tokens": "sekret:admin"})()
    )
    ctx = FakeContext(FakeRequest(FakeHeaders({"authorization": "Bearer wrong-token"})))
    with pytest.raises(UnauthorizedError):
        tmcp_auth.resolve_actor(ctx)  # type: ignore[arg-type]


def test_require_min_role_raises_forbidden_when_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TASK_MCP_STDIO_ROLE", "viewer")
    with pytest.raises(ForbiddenError):
        tmcp_auth.require_min_role(None, Role.ADMIN)


def test_require_min_role_passes_when_sufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASK_MCP_STDIO_ROLE", "admin")
    actor_ctx = tmcp_auth.require_min_role(None, Role.USER)
    assert actor_ctx.role == Role.ADMIN
