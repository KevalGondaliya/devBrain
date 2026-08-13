"""`GET /projects` — thin wrapper over
`project_mcp.services.projects_service.list_projects`, for Phase 9's
Projects page (DevBrain_vision.md §20's "Show project health" — this
endpoint supplies the underlying project list; per-project health detail
is `devbrain_backend.agents.project_health.analyze_project_health`, reached
via `/chat`'s `project_health` intent in this phase)."""

from __future__ import annotations

from devbrain_common.auth import Role
from devbrain_common.mcp_auth import ActorContext
from devbrain_common.mcp_tooling import dto_to_dict
from fastapi import APIRouter, Depends
from project_mcp.services import projects_service

from devbrain_backend.api.auth import require_role
from devbrain_backend.api.schemas import ProjectOut, ProjectsResponse

router = APIRouter(tags=["projects"])

# Module-level singleton, evaluated once at import time — see
# `permissions_router.py`'s identical comment for why (ruff B008).
_require_viewer = Depends(require_role(Role.VIEWER))


@router.get("/projects", response_model=ProjectsResponse)
async def get_projects(_actor_ctx: ActorContext = _require_viewer) -> ProjectsResponse:
    projects = await projects_service.list_projects()
    return ProjectsResponse(projects=[ProjectOut(**dto_to_dict(p)) for p in projects])
