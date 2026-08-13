"""Cross-System Investigation — DevBrain_vision.md §7 ("Example End-to-End
Workflow") / §8 ("Flagship Workflow") / §31 (Flagship Demo #3), all three
built around the same "why is my MCP project blocked?" question.

Chains Project MCP -> Task MCP -> Knowledge MCP -> GitHub MCP exactly per
§8's diagram, then synthesizes a single answer via the LLM client that
explicitly cites which system each fact came from. Read-only.
"""

from __future__ import annotations

from dataclasses import dataclass

from devbrain_common.llm import LLMClient, build_prompt, get_llm_client
from knowledge_mcp.services import decisions_service as decisions_service
from knowledge_mcp.services import meetings_service as meetings_service
from project_mcp.services import projects_service as projects_service
from task_mcp.services import tasks_service as tasks_service

from devbrain_backend.agents._common import github_activity_for_project

_INSTRUCTIONS = (
    "You are DevBrain's cross-system investigator. A user asked why one of "
    "their projects is blocked or behind. Using only the structured data "
    "below — gathered from the Project, Task, Knowledge, and GitHub systems "
    "— write a short answer that explicitly cites which system each fact "
    "came from (e.g. 'Project MCP shows...', 'Task MCP shows...', "
    "'Knowledge MCP surfaces the decision...', 'GitHub shows...') and ends "
    "with one recommended next action. If a system has no relevant data, "
    "say so briefly rather than omitting it silently."
)


@dataclass(frozen=True)
class InvestigationResult:
    project_id: str
    project_name: str
    project_status: str
    answer: str
    blocked_task_count: int
    relevant_decision_count: int
    relevant_meeting_count: int
    github_activity_count: int


async def investigate_project_blockage(
    *, project_id: str, llm: LLMClient | None = None
) -> InvestigationResult:
    llm = llm or get_llm_client()

    project = await projects_service.get_project(project_id=project_id)
    status = await projects_service.get_project_status(project_id=project_id)

    blockers = await tasks_service.list_tasks(project_id=project_id, status="blocked")
    decisions = await decisions_service.search_decisions(query=project.name, limit=5)
    meetings = await meetings_service.search_meetings(query=project.name, limit=5)
    github_items = await github_activity_for_project(project.name)

    data = {
        "project_mcp": {
            "project_name": project.name,
            "status": status.status,
            "priority": status.priority,
        },
        "task_mcp_blockers": [{"title": t.title, "reason": t.blocked_reason} for t in blockers],
        "knowledge_mcp_decisions": [
            {"title": d.title, "decision": d.decision, "reasoning": d.reasoning} for d in decisions
        ],
        "knowledge_mcp_meetings": [{"title": m.title, "date": m.date} for m in meetings],
        "github_mcp_activity": [
            {"type": g.type, "title": g.title, "status": g.status} for g in github_items
        ],
    }
    prompt = build_prompt(instructions=_INSTRUCTIONS, data=data)
    answer = await llm.complete(prompt, system=_INSTRUCTIONS)

    return InvestigationResult(
        project_id=str(project.id),
        project_name=project.name,
        project_status=status.status,
        answer=answer,
        blocked_task_count=len(blockers),
        relevant_decision_count=len(decisions),
        relevant_meeting_count=len(meetings),
        github_activity_count=len(github_items),
    )
