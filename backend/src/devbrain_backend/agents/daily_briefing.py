"""Daily Developer Briefing — DevBrain_vision.md §27 (Flagship Demo #1).

Gathers today's calendar events, priority tasks, blocked-task reasons,
recent decisions, and GitHub activity across the user's active projects,
then synthesizes them into a single narrative briefing via the pluggable
LLM client (`devbrain_common.llm.get_llm_client`). See `agents/__init__.py`
for why this is structurally an *agent* (multi-step, stateful, calls five
services' worth of read functions) rather than a single deterministic tool
call.

Read-only: no service call here ever passes a `role`/`approval_id` — no
write happens in this orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from calendar_mcp.services import calendar_service as calendar_service
from devbrain_common.errors import NotFoundError
from devbrain_common.llm import LLMClient, build_prompt, get_llm_client
from github_mcp.services import github_service as github_service
from knowledge_mcp.services import decisions_service as decisions_service
from project_mcp.services import projects_service as projects_service
from task_mcp.services import tasks_service as tasks_service

from devbrain_backend.agents._common import github_activity_for_project

_INSTRUCTIONS = (
    "You are DevBrain's daily developer briefing assistant. Using only the "
    "structured data below (gathered from Calendar, Task, Project, "
    "Knowledge, and GitHub systems), write a concise 'Daily Developer "
    "Briefing' with clearly labeled sections: Calendar, Priority Tasks, "
    "Blocked, Recent Decisions, GitHub, and a final Recommendation sentence "
    "naming the single most important next action. Do not invent facts not "
    "present in the data."
)

MAX_PRIORITY_TASKS = 5
MAX_RECENT_DECISIONS = 5
MAX_GITHUB_ITEMS = 5


@dataclass(frozen=True)
class DailyBriefingResult:
    briefing_text: str
    calendar_event_count: int
    priority_task_count: int
    blocked_task_count: int
    recent_decision_count: int
    github_activity_count: int


def _task_line(task: tasks_service.TaskDTO) -> dict[str, Any]:
    return {
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date.isoformat() if task.due_date else None,
    }


async def _projects_touched_by(
    tasks: list[tasks_service.TaskDTO],
) -> dict[str, projects_service.ProjectDTO]:
    """Resolve the distinct `project_id`s referenced by `tasks` into
    `ProjectDTO`s, skipping any that no longer exist (never let a stale
    task/project reference break the whole briefing)."""
    projects: dict[str, projects_service.ProjectDTO] = {}
    for project_id in {t.project_id for t in tasks}:
        if project_id in projects:
            continue
        try:
            projects[project_id] = await projects_service.get_project(project_id=project_id)
        except NotFoundError:
            continue
    return projects


async def generate_daily_briefing(*, llm: LLMClient | None = None) -> DailyBriefingResult:
    llm = llm or get_llm_client()

    events = await calendar_service.get_today_events()

    all_tasks = await tasks_service.list_tasks()
    priority_tasks = [
        t for t in all_tasks if t.priority == "high" and t.status in ("todo", "in_progress")
    ][:MAX_PRIORITY_TASKS]
    blocked_tasks = [t for t in all_tasks if t.status == "blocked"]

    # `knowledge_mcp.search_decisions`/`github_mcp.search_issues` both
    # require a non-empty query — the project name is used as a natural
    # search term (per DevBrain_vision.md §7's own example workflow, which
    # chains `search_decisions`/`search_github` off a project's context),
    # scoped to the projects actually surfaced by the tasks above.
    relevant_projects = await _projects_touched_by(priority_tasks + blocked_tasks)

    recent_decisions: list[decisions_service.DecisionDTO] = []
    seen_decision_ids: set[str] = set()
    github_items: list[github_service.GithubActivityDTO] = []
    seen_github_ids: set[str] = set()
    for project in relevant_projects.values():
        for decision in await decisions_service.search_decisions(query=project.name, limit=3):
            if decision.id not in seen_decision_ids:
                seen_decision_ids.add(decision.id)
                recent_decisions.append(decision)
        for item in await github_activity_for_project(project.name, pr_limit=3, issue_limit=3):
            if item.id not in seen_github_ids:
                seen_github_ids.add(item.id)
                github_items.append(item)
    recent_decisions = recent_decisions[:MAX_RECENT_DECISIONS]
    github_items = github_items[:MAX_GITHUB_ITEMS]

    data = {
        "calendar": [{"title": e.title, "starts_at": e.starts_at.isoformat()} for e in events],
        "priority_tasks": [_task_line(t) for t in priority_tasks],
        "blocked": [{"title": t.title, "reason": t.blocked_reason} for t in blocked_tasks],
        "recent_decisions": [{"title": d.title, "decision": d.decision} for d in recent_decisions],
        "github": [
            {"repository": g.repository, "type": g.type, "title": g.title, "status": g.status}
            for g in github_items
        ],
    }
    prompt = build_prompt(instructions=_INSTRUCTIONS, data=data)
    briefing_text = await llm.complete(prompt, system=_INSTRUCTIONS)

    return DailyBriefingResult(
        briefing_text=briefing_text,
        calendar_event_count=len(events),
        priority_task_count=len(priority_tasks),
        blocked_task_count=len(blocked_tasks),
        recent_decision_count=len(recent_decisions),
        github_activity_count=len(github_items),
    )
