"""`POST /chat` — Phase 9's frontend chat page needs *something* to call;
this is deliberately a pragmatic, honestly-limited router, not a full
agentic tool-use loop.

**What this is**: keyword matching against the incoming message, routing to
one of the five Phase 7 flagship orchestrators when the message clearly
names its intent (and, for the two project-scoped ones, when a real
project's name also appears verbatim in the message), otherwise a direct
`LLMClient.complete()` call over the conversation alone.

**What this deliberately is not** (documented honestly, not hidden):
- Claude never decides which orchestrator to call — there is no tool-use
  loop, no function-calling schema, no multi-step planning. A message that
  describes an intent in different words than `_INTENT_KEYWORDS` simply
  falls through to the direct-completion branch.
- `project_health`/`cross_system_investigation` only fire when a project's
  *exact* name (case-insensitive) is found as a substring of the message —
  same class of best-effort heuristic as
  `agents/_common.py::repository_slug_for_project`. No fuzzy matching, no
  disambiguation prompt if multiple projects could match (first match
  wins).
- `safe_write` is *recognized* (so a user asking to "create a task" gets a
  clear, correct answer) but is **never** auto-executed from freeform text.
  This codebase never lets natural-language input construct a write tool's
  `arguments` dict directly — that is exactly the prompt-injection posture
  every other phase of this project enforces (see
  `devbrain_common.llm`'s module docstring and
  `backend/src/devbrain_backend/agents/safe_write.py`). A real proposal
  needs the exact structured fields `safe_write.propose_create_task` (or
  the `POST /approvals/*` endpoints once a proposal already exists) expects
  — chat text alone is not a trustworthy source for those.
"""

from __future__ import annotations

from typing import Literal

from devbrain_common.auth import Role, check_role
from devbrain_common.llm import build_prompt, get_llm_client
from devbrain_common.mcp_auth import ActorContext
from devbrain_common.mcp_tooling import dto_to_dict
from fastapi import APIRouter, Depends
from project_mcp.services import projects_service

from devbrain_backend.agents.cross_system_investigation import investigate_project_blockage
from devbrain_backend.agents.daily_briefing import generate_daily_briefing
from devbrain_backend.agents.project_health import analyze_project_health
from devbrain_backend.agents.weekly_digest import generate_weekly_digest
from devbrain_backend.api.auth import require_role
from devbrain_backend.api.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])

Intent = Literal[
    "daily_briefing",
    "weekly_digest",
    "safe_write",
    "project_health",
    "cross_system_investigation",
    "none",
]

# Order matters: checked top-to-bottom, first match wins, so a message
# containing more than one keyword resolves to the earlier (more specific)
# intent rather than whichever key iteration happened to hit first.
_INTENT_KEYWORDS: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    ("weekly_digest", ("weekly digest",)),
    ("daily_briefing", ("daily briefing", "daily brief")),
    (
        "safe_write",
        ("create a task", "create task", "propose a task", "propose task", "safe write"),
    ),
    ("project_health", ("project health", "health of", "how healthy")),
    (
        "cross_system_investigation",
        ("why is", "why's", "investigate", "blocked", "behind schedule"),
    ),
)

_DIRECT_INSTRUCTIONS = (
    "You are DevBrain's chat assistant. Answer the user's message helpfully "
    "using only the conversation below. You have no live access to "
    "DevBrain's project/task/knowledge/GitHub/calendar data in this reply — "
    "if the question needs that, say so and suggest asking about a specific "
    "project by name, or one of: daily briefing, weekly digest, project "
    "health, or why a project is blocked."
)

_SAFE_WRITE_REPLY = (
    "I can't create a task directly from chat text — DevBrain never lets "
    "freeform input author a write tool's arguments (see "
    "devbrain_backend/agents/safe_write.py). Propose the task with its "
    "exact fields (project, title, priority, ...) through the safe-write "
    "flow, then have an admin approve it via POST /approvals/{id}/decide."
)


def _detect_intent(message: str) -> Intent:
    lowered = message.lower()
    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "none"


async def _find_project(message: str) -> projects_service.ProjectDTO | None:
    """Best-effort: does any known project's name appear (case-insensitive
    substring) in `message`? Returns the first match or `None` — a miss
    just means the caller falls back to a direct completion, never an
    error."""
    lowered = message.lower()
    for project in await projects_service.list_projects():
        if project.name.lower() in lowered:
            return project
    return None


async def _direct_completion(body: ChatRequest) -> ChatResponse:
    llm = get_llm_client()
    history_lines = [f"{m.role}: {m.content}" for m in body.history]
    prompt = build_prompt(
        instructions=_DIRECT_INSTRUCTIONS,
        data={"conversation_history": history_lines, "message": body.message},
    )
    reply = await llm.complete(prompt, system=_DIRECT_INSTRUCTIONS)
    return ChatResponse(reply=reply, intent="none", orchestrator=None, data={})


# Module-level singleton, evaluated once at import time — see
# `permissions_router.py`'s identical comment for why (ruff B008).
_require_viewer = Depends(require_role(Role.VIEWER))


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, actor_ctx: ActorContext = _require_viewer) -> ChatResponse:
    intent = _detect_intent(body.message)

    if intent == "daily_briefing":
        briefing = await generate_daily_briefing()
        return ChatResponse(
            reply=briefing.briefing_text,
            intent=intent,
            orchestrator="daily_briefing",
            data=dto_to_dict(briefing),
        )

    if intent == "weekly_digest":
        # Creates a new note — a write, so this needs Role.USER even though
        # the /chat endpoint's own minimum is Role.VIEWER (read-only chat
        # is fine for a viewer; this one branch is not).
        check_role(actor_ctx.role, Role.USER)
        digest = await generate_weekly_digest(actor=actor_ctx.actor)
        reply = (
            f"Created '{digest.digest_note.title}' from "
            f"{digest.source_note_count} note(s) written in the last 7 days."
        )
        return ChatResponse(
            reply=reply, intent=intent, orchestrator="weekly_digest", data=dto_to_dict(digest)
        )

    if intent == "safe_write":
        return ChatResponse(reply=_SAFE_WRITE_REPLY, intent=intent, orchestrator=None, data={})

    if intent in ("project_health", "cross_system_investigation"):
        project = await _find_project(body.message)
        if project is not None:
            if intent == "project_health":
                health = await analyze_project_health(project_id=project.id)
                return ChatResponse(
                    reply=health.narrative,
                    intent=intent,
                    orchestrator="project_health",
                    data=dto_to_dict(health),
                )
            investigation = await investigate_project_blockage(project_id=project.id)
            return ChatResponse(
                reply=investigation.answer,
                intent=intent,
                orchestrator="cross_system_investigation",
                data=dto_to_dict(investigation),
            )
        # No known project named in the message — fall through below rather
        # than guessing which project the user meant.

    return await _direct_completion(body)
