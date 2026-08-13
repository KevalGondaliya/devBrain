"""`POST /auth/login` — exchange a static `MCP_API_TOKENS` bearer token for
its resolved role. Doesn't issue a session of its own: the token itself
*is* the credential, exactly like every MCP tool's HTTP transport already
works (`devbrain_common.mcp_auth.build_actor_resolver`) — the frontend
re-sends the same token as `Authorization: Bearer <token>` on every later
request (see `devbrain_backend.api.auth.require_role`). This endpoint just
lets a login form confirm the token is valid and show the resolved role
before the user starts issuing other requests.
"""

from __future__ import annotations

from devbrain_common.auth import TokenStore
from devbrain_common.config import get_settings
from fastapi import APIRouter

from devbrain_backend.api.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    store = TokenStore.from_env_value(get_settings().mcp_api_tokens)
    # Raises `UnauthorizedError` for an unrecognized token -> 401, handled
    # by `main.py`'s global `DevBrainError` exception handler.
    role = store.authenticate(body.token)
    return LoginResponse(role=role.value, actor=f"token:{body.token[:4]}***")
