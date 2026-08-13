"""Auth primitives: role model + static bearer token parsing.

This module is primitives-only. Wiring these into the MCP transport (reading
the `Authorization` header, attaching a role to the request context) happens
in Phase 6 — see ORCHESTRATION.md phase table. What must be solid *now*:
- `Role` ordering (viewer < user < admin), matching DevBrain_vision.md §12.
- Parsing `MCP_API_TOKENS` ("token:role,token:role") into a lookup.
- A `require_role(min_role)` guard that later tool wrappers can reuse.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, TypeVar

from devbrain_common.errors import ForbiddenError, UnauthorizedError

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


class Role(StrEnum):
    """Actor role, ordered least → most privileged.

    DevBrain_vision.md §12:
      - viewer: read only
      - user: read + normal task/note/project write operations
      - admin: sensitive/destructive actions
    """

    VIEWER = "viewer"
    USER = "user"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]

    def at_least(self, other: Role) -> bool:
        """True if this role is >= `other` in privilege."""
        return self.rank >= other.rank


_ROLE_RANK: dict[Role, int] = {Role.VIEWER: 0, Role.USER: 1, Role.ADMIN: 2}


class TokenParseError(ValueError):
    """Raised when `MCP_API_TOKENS` is malformed."""


def parse_tokens(raw: str) -> dict[str, Role]:
    """Parse `MCP_API_TOKENS` ("token:role,token:role") into a token->Role map.

    Blank/whitespace-only input yields an empty map (no tokens configured).
    Each entry must be `token:role` with a role that matches `Role`'s
    values; malformed entries raise `TokenParseError` (fail closed rather
    than silently dropping a bad entry, since that could unintentionally
    lock out or, worse, mis-scope an actor).
    """
    raw = raw.strip()
    if not raw:
        return {}

    tokens: dict[str, Role] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) != 2:
            raise TokenParseError(f"malformed MCP_API_TOKENS entry: {entry!r}")
        token, role_str = (p.strip() for p in parts)
        if not token:
            raise TokenParseError(f"malformed MCP_API_TOKENS entry (empty token): {entry!r}")
        try:
            role = Role(role_str)
        except ValueError as exc:
            raise TokenParseError(
                f"unknown role {role_str!r} in MCP_API_TOKENS entry: {entry!r}"
            ) from exc
        tokens[token] = role
    return tokens


class TokenStore:
    """Lookup wrapper around a parsed token->Role map."""

    def __init__(self, tokens: dict[str, Role]) -> None:
        self._tokens = tokens

    @classmethod
    def from_env_value(cls, raw: str) -> TokenStore:
        return cls(parse_tokens(raw))

    def resolve(self, token: str) -> Role | None:
        """Return the `Role` for a bearer token, or `None` if unrecognized."""
        return self._tokens.get(token)

    def authenticate(self, token: str) -> Role:
        """Return the `Role` for a bearer token, raising `UnauthorizedError` if unknown."""
        role = self.resolve(token)
        if role is None:
            raise UnauthorizedError("Invalid or unrecognized API token.")
        return role


def check_role(role: Role, min_role: Role) -> None:
    """Raise `ForbiddenError` if `role` does not meet `min_role`."""
    if not role.at_least(min_role):
        raise ForbiddenError(
            f"This action requires role '{min_role.value}' or higher; caller has '{role.value}'."
        )


def require_role(min_role: Role) -> Callable[[F], F]:
    """Decorator for async tool-wrapper functions that must enforce a minimum role.

    The wrapped function must be called with a `role: Role` keyword argument
    (later phases' MCP tool wrappers resolve this from the auth context
    before dispatching to the underlying tool). Raises `ForbiddenError` if
    the caller's role is insufficient; the wrapped function is not invoked.

    Usage:
        @require_role(Role.ADMIN)
        async def delete_project(*, role: Role, project_id: str) -> None:
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            role = kwargs.get("role")
            if role is None:
                raise UnauthorizedError("No role provided for a role-guarded call.")
            check_role(role, min_role)
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
