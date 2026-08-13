"""DevBrain backend — FastAPI HTTP surface (Phase 8), the HTTP layer Phase
9's Next.js frontend calls.

Thin layer over Phases 3-7: every endpoint calls straight into an existing
`services/*.py` function, a `backend/src/devbrain_backend/agents/*.py`
orchestrator, or a `devbrain_common` primitive (auth/approvals/risk) — no
new business logic lives under `api/`. See each router module's own
docstring for what it wraps.

**CORS**: wide open (`allow_origins=["*"]`, no credentials). This is a
**local-dev/demo configuration only** — before any real deployment, narrow
`allow_origins` to the actual frontend origin(s). `allow_credentials=False`
is deliberate alongside the wildcard (browsers refuse `*` combined with
credentialed requests anyway, and this project's auth is a bearer token in
an `Authorization` header, not a cookie, so credentialed CORS was never
needed here).
"""

from __future__ import annotations

from devbrain_common.errors import DevBrainError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from devbrain_backend.api.routers import (
    activity_router,
    approvals_router,
    auth_router,
    chat_router,
    permissions_router,
    projects_router,
    tools_router,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="DevBrain Backend",
        description="HTTP surface over DevBrain's five MCP services and Phase 7 orchestrators.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DevBrainError)
    async def _devbrain_error_handler(_request: Request, exc: DevBrainError) -> JSONResponse:
        # ORCHESTRATION.md §1: "Structured errors only" — every
        # `DevBrainError` (raised by `devbrain_common.auth`/`approvals`/
        # every service function this API wraps) already carries the right
        # HTTP status; this is the one place that translation happens for
        # the whole app, matching every MCP tool's own
        # `handle_tool_errors`-> `{"error": {"code","message"}}` envelope.
        return JSONResponse(status_code=exc.http_status, content=exc.to_error_envelope())

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router.router)
    app.include_router(chat_router.router)
    app.include_router(activity_router.router)
    app.include_router(permissions_router.router)
    app.include_router(projects_router.router)
    app.include_router(tools_router.router)
    app.include_router(approvals_router.router)

    return app


app = create_app()
