"""Project Health Analysis — DevBrain_vision.md §10 ("Human-in-the-Loop
Policy" context) / §29 (Flagship Demo #3 numbering) / Phase 10's own
"Project Health Analysis" build-phase section.

Gathers project status, tasks (open/blocked/overdue), recent meetings,
recent decisions, and GitHub activity for one project. `compute_verdict`
is a pure, deterministic function (no LLM call) so the
ON_TRACK/AT_RISK/BLOCKED verdict is identical whether `DEVBRAIN_LLM_MODE`
is `stub` or `real` — the LLM client is used only for the narrative
"reasons"/"recommendations" synthesis on top of an already-decided verdict,
matching §10's "the AI should never be the final authorization authority"
posture (here: never the final *health-classification* authority either).

Read-only — no write happens here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from devbrain_common.llm import LLMClient, build_prompt, get_llm_client
from knowledge_mcp.services import decisions_service as decisions_service
from knowledge_mcp.services import meetings_service as meetings_service
from project_mcp.services import projects_service as projects_service
from task_mcp.services import tasks_service as tasks_service

from devbrain_backend.agents._common import github_activity_for_project

Verdict = Literal["ON_TRACK", "AT_RISK", "BLOCKED"]

_INSTRUCTIONS = (
    "You are DevBrain's project health analyst. Using only the structured "
    "data below, write the 'Reasons' (a short bulleted explanation) and "
    "'Recommendations' (concrete next actions) sections of a project health "
    "report. The verdict field in the data is already decided by the "
    "calling system — explain and recommend against that given verdict, do "
    "not propose a different one."
)


@dataclass(frozen=True)
class ProjectHealthResult:
    project_id: str
    project_name: str
    verdict: Verdict
    narrative: str
    open_task_count: int
    blocked_task_count: int
    overdue_task_count: int
    recent_meeting_count: int
    recent_decision_count: int
    github_activity_count: int


def compute_verdict(
    *, project_status: str, blocked_task_count: int, overdue_task_count: int
) -> Verdict:
    """Pure, deterministic health classification — no LLM involved, so this
    is directly unit-testable and identical in `stub`/`real` LLM mode.

    `BLOCKED` if the project itself is marked blocked or has any blocked
    task; else `AT_RISK` if anything is overdue; else `ON_TRACK`.
    """
    if project_status == "blocked" or blocked_task_count > 0:
        return "BLOCKED"
    if overdue_task_count > 0:
        return "AT_RISK"
    return "ON_TRACK"


async def analyze_project_health(
    *, project_id: str, llm: LLMClient | None = None
) -> ProjectHealthResult:
    llm = llm or get_llm_client()

    project = await projects_service.get_project(project_id=project_id)
    tasks = await tasks_service.list_tasks(project_id=project_id)
    now = datetime.now(tz=UTC)
    open_tasks = [t for t in tasks if t.status in ("todo", "in_progress")]
    blocked_tasks = [t for t in tasks if t.status == "blocked"]
    overdue_tasks = [t for t in open_tasks if t.due_date is not None and t.due_date < now]

    meetings = await meetings_service.search_meetings(query=project.name, limit=5)
    decisions = await decisions_service.search_decisions(query=project.name, limit=5)
    github_items = await github_activity_for_project(project.name)

    verdict = compute_verdict(
        project_status=project.status,
        blocked_task_count=len(blocked_tasks),
        overdue_task_count=len(overdue_tasks),
    )

    data = {
        "project_name": project.name,
        "project_status": project.status,
        "verdict": verdict,
        "open_tasks": [{"title": t.title, "priority": t.priority} for t in open_tasks],
        "blocked_tasks": [{"title": t.title, "reason": t.blocked_reason} for t in blocked_tasks],
        "overdue_tasks": [
            {"title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None}
            for t in overdue_tasks
        ],
        "recent_meetings": [{"title": m.title, "date": m.date} for m in meetings],
        "recent_decisions": [{"title": d.title, "decision": d.decision} for d in decisions],
        "github_activity": [
            {"type": g.type, "title": g.title, "status": g.status} for g in github_items
        ],
    }
    prompt = build_prompt(instructions=_INSTRUCTIONS, data=data)
    narrative = await llm.complete(prompt, system=_INSTRUCTIONS)

    return ProjectHealthResult(
        project_id=str(project.id),
        project_name=project.name,
        verdict=verdict,
        narrative=narrative,
        open_task_count=len(open_tasks),
        blocked_task_count=len(blocked_tasks),
        overdue_task_count=len(overdue_tasks),
        recent_meeting_count=len(meetings),
        recent_decision_count=len(decisions),
        github_activity_count=len(github_items),
    )
