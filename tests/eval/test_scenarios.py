"""Evaluation scenario runner — `DevBrain_vision.md` §26 ("Evaluation
Dataset", 30-50 scenarios), scenarios defined in `tests/eval/scenarios.json`.

**What this proves, honestly**: for each scenario's natural-language-ish
question, the designated `entrypoint` runner invokes the *real*
orchestrator/service function(s) DevBrain would use to answer it (under
`DEVBRAIN_LLM_MODE=stub` — no live Anthropic API key needed, see
`packages/common/src/devbrain_common/llm.py`) against a real seeded
`db_test`, and this test asserts the expected underlying service calls
actually happened (via `monkeypatch`-installed spies) and, for write
scenarios, that the approval gate behaves as `DevBrain_vision.md` §26
expects (required / not required, admin-and-approval-together for the one
high-risk tool).

**What this does NOT prove**: that Claude itself, given the question in
free text with no `entrypoint` hint, would choose to call these same
functions. There is no live LLM tool-selection step here — `entrypoint` is
a fixed, hand-written mapping from scenario to runner, decided by this test
file's author, not discovered by an agent at run time. That gap is real and
is not hidden: a true agentic eval needs a live Claude Code/Desktop MCP
connection driving real tool-use, which is exactly what `DEMO.md` exercises
manually. This suite is the CI-friendly proxy for "the right service call
exists and behaves correctly when invoked" — necessary but not sufficient
for "Claude picks it every time."

Run: `docker compose --profile test up -d db_test` then
`.venv/bin/python -m pytest tests/eval -q` from repo root.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from calendar_mcp.services import calendar_service
from devbrain_backend.agents import safe_write
from devbrain_backend.agents.cross_system_investigation import investigate_project_blockage
from devbrain_backend.agents.daily_briefing import generate_daily_briefing
from devbrain_backend.agents.project_health import analyze_project_health
from devbrain_backend.agents.weekly_digest import generate_weekly_digest
from devbrain_common.approvals import decide_approval
from devbrain_common.auth import Role
from devbrain_common.errors import ApprovalRequiredError, ForbiddenError
from github_mcp.services import github_service
from knowledge_mcp.services import (
    decisions_service,
    links_service,
    meetings_service,
    notes_service,
    search_service,
    tags_service,
)
from project_mcp.services import projects_service
from sqlalchemy.ext.asyncio import AsyncSession
from task_mcp.services import tasks_service

# `tests/eval/conftest.py` puts `scripts/` on sys.path (to import
# `generate_all` for seeding) before this module is collected, same
# pattern every other integration conftest in this repo uses.
from generators.notes import PROMPT_INJECTION_SLUG

_SCENARIOS_PATH = Path(__file__).parent / "scenarios.json"

_ERROR_TYPES: dict[str, type[Exception]] = {
    "ApprovalRequiredError": ApprovalRequiredError,
    "ForbiddenError": ForbiddenError,
}


@dataclass
class CallSpy:
    """Wraps an async function, counting invocations while still calling
    through to the real implementation — so a scenario both proves "this
    call happened" and still exercises real business logic/DB access."""

    original: Callable[..., Awaitable[Any]]
    calls: int = field(default=0, init=False)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        return await self.original(*args, **kwargs)


def _install_spy(monkeypatch: pytest.MonkeyPatch, target: str) -> CallSpy:
    module_path, func_name = target.split(":")
    module = importlib.import_module(module_path)
    original = getattr(module, func_name)
    spy = CallSpy(original)
    monkeypatch.setattr(module, func_name, spy)
    return spy


def load_scenarios() -> list[dict[str, Any]]:
    payload = json.loads(_SCENARIOS_PATH.read_text())
    scenarios: list[dict[str, Any]] = payload["scenarios"]
    return scenarios


async def _first_project(session: AsyncSession) -> projects_service.ProjectDTO:
    projects = await projects_service.list_projects()
    assert projects, "seeded dataset must contain at least one project"
    return projects[0]


async def _first_task(session: AsyncSession) -> tasks_service.TaskDTO:
    tasks = await tasks_service.list_tasks()
    assert tasks, "seeded dataset must contain at least one task"
    return tasks[0]


# --- Runners: one per `entrypoint` value in scenarios.json. Each performs
# the real call(s) a competent agent would make to answer the scenario's
# question, against the real service/orchestrator layer. ---


async def daily_briefing(session: AsyncSession) -> None:
    await generate_daily_briefing()


async def project_health(session: AsyncSession) -> None:
    project = await _first_project(session)
    await analyze_project_health(project_id=project.id)


async def cross_system_investigation(session: AsyncSession) -> None:
    project = await _first_project(session)
    await investigate_project_blockage(project_id=project.id)


async def weekly_digest(session: AsyncSession) -> None:
    await generate_weekly_digest(actor="eval-suite")


async def decision_lookup(session: AsyncSession) -> None:
    hits = await decisions_service.search_decisions(query="database")
    assert hits, "expected the seeded MongoDB/PostgreSQL decision pair to match 'database'"
    await decisions_service.get_decision(decision_id=hits[0].id)


async def decision_get_by_id(session: AsyncSession) -> None:
    await decision_lookup(session)


async def oauth_status_check(session: AsyncSession) -> None:
    await tasks_service.search_tasks(query="OAuth")
    await github_service.search_issues(query="OAuth")


async def meeting_lookup(session: AsyncSession) -> None:
    project = await _first_project(session)
    hits = await meetings_service.search_meetings(query=project.name)
    if hits:
        await meetings_service.read_meeting(meeting_id=hits[0].id)
    else:
        # A miss is a legitimate outcome for a generic project name search
        # against seeded meetings -- fall back to a broad query so the tool
        # sequence (search then read) is still exercised for real.
        hits = await meetings_service.search_meetings(query="meeting")
        if hits:
            await meetings_service.read_meeting(meeting_id=hits[0].id)


async def notes_search_hybrid(session: AsyncSession) -> None:
    await search_service.search_notes(query="oauth", mode="hybrid")


async def notes_backlinks(session: AsyncSession) -> None:
    note = await notes_service.get_note(slug=PROMPT_INJECTION_SLUG)
    await links_service.get_backlinks(note_id=note.id)


async def notes_graph(session: AsyncSession) -> None:
    note = await notes_service.get_note(slug=PROMPT_INJECTION_SLUG)
    await links_service.get_graph(note_id=note.id, depth=2)


async def tags_list(session: AsyncSession) -> None:
    await tags_service.list_tags()


async def tasks_list_all(session: AsyncSession) -> None:
    await tasks_service.list_tasks()


async def tasks_search_general(session: AsyncSession) -> None:
    await tasks_service.search_tasks(query="migration")


async def task_get_single(session: AsyncSession) -> None:
    task = await _first_task(session)
    await tasks_service.get_task(task_id=task.id)


async def github_open_prs(session: AsyncSession) -> None:
    project = await _first_project(session)
    await github_service.list_pull_requests(repository=f"devbrain-org/{project.name.lower()}")


async def github_issue_search(session: AsyncSession) -> None:
    await github_service.search_issues(query="bug")


async def github_commit_search(session: AsyncSession) -> None:
    await github_service.search_commits(query="fix")


async def github_repo_activity(session: AsyncSession) -> None:
    project = await _first_project(session)
    await github_service.get_repository_activity(repository=f"devbrain-org/{project.name.lower()}")


async def github_get_issue_detail(session: AsyncSession) -> None:
    hits = await github_service.search_issues(query="a")
    if hits:
        await github_service.get_issue(issue_id=hits[0].id)


async def calendar_today(session: AsyncSession) -> None:
    await calendar_service.get_today_events()


async def calendar_week(session: AsyncSession) -> None:
    await calendar_service.get_week_events()


async def calendar_find(session: AsyncSession) -> None:
    await calendar_service.find_event(query="review")


async def projects_list_all(session: AsyncSession) -> None:
    await projects_service.list_projects()


async def projects_search(session: AsyncSession) -> None:
    project = await _first_project(session)
    await projects_service.search_projects(query=project.name[:4])


async def project_status_check(session: AsyncSession) -> None:
    project = await _first_project(session)
    await projects_service.get_project_status(project_id=project.id)


async def create_task_without_approval(session: AsyncSession) -> None:
    project = await _first_project(session)
    proposal = await safe_write.propose_create_task(
        actor="eval-suite", project_id=project.id, title="Fix the OAuth tests", priority="high"
    )
    # No decide_approval call -> the approved retry must be refused.
    await safe_write.execute_approved_task_creation(
        actor="eval-suite",
        approval_id=proposal.approval_id,
        project_id=project.id,
        title="Fix the OAuth tests",
        priority="high",
    )


async def create_task_full_round_trip(session: AsyncSession) -> None:
    project = await _first_project(session)
    proposal = await safe_write.propose_create_task(
        actor="eval-suite", project_id=project.id, title="Fix the OAuth tests", priority="high"
    )
    await decide_approval(
        session, approval_id=proposal.approval_id, decision="approved", decided_by="eval-admin"
    )
    task = await safe_write.execute_approved_task_creation(
        actor="eval-suite",
        approval_id=proposal.approval_id,
        project_id=project.id,
        title="Fix the OAuth tests",
        priority="high",
    )
    assert task.title == "Fix the OAuth tests"


async def update_project_status_without_approval(session: AsyncSession) -> None:
    project = await _first_project(session)
    await projects_service.update_project_status(
        project_id=project.id, status="blocked", actor="eval-suite", role=Role.USER
    )


async def complete_task_without_approval(session: AsyncSession) -> None:
    task = await _first_task(session)
    await tasks_service.complete_task(task_id=task.id, actor="eval-suite", role=Role.USER)


async def tags_rename_without_approval(session: AsyncSession) -> None:
    await tags_service.rename_tag(
        old_name="python", new_name="python-eval-renamed", actor="eval-suite", role=Role.USER
    )


async def notes_create_without_approval(session: AsyncSession) -> None:
    await notes_service.create_note(
        title="Today's decisions",
        content_md="Summary of what we decided today.",
        actor="eval-suite",
        role=Role.USER,
    )


async def calendar_create_event_without_approval(session: AsyncSession) -> None:
    await calendar_service.create_event(
        title="Follow-up meeting",
        starts_at="2026-08-14T10:00:00+00:00",
        ends_at="2026-08-14T11:00:00+00:00",
        actor="eval-suite",
        role=Role.USER,
    )


async def high_risk_delete_requires_admin_and_approval(session: AsyncSession) -> None:
    """Role.USER, no approval -- the transport-level `require_min_role`
    equivalent enforced here at the service layer: non-admin is rejected
    outright, before an approval is even considered."""
    note = await notes_service.get_note(slug=PROMPT_INJECTION_SLUG)
    await notes_service.delete_note(note_id=note.id, actor="eval-suite", role=Role.USER)


async def high_risk_delete_admin_without_approval(session: AsyncSession) -> None:
    """Role.ADMIN alone, no approval -- still refused. Admin status does
    not waive approval for a HIGH-risk tool (docs/mcp/tool-design.md)."""
    note = await notes_service.get_note(slug=PROMPT_INJECTION_SLUG)
    await notes_service.delete_note(note_id=note.id, actor="eval-suite", role=Role.ADMIN)


async def malicious_note_summary(session: AsyncSession) -> None:
    note = await notes_service.get_note(slug=PROMPT_INJECTION_SLUG)
    assert "ignore all previous instructions" in note.content.lower()


async def malicious_note_follow_instructions(session: AsyncSession) -> None:
    await malicious_note_summary(session)


RUNNERS: dict[str, Callable[[AsyncSession], Awaitable[None]]] = {
    "daily_briefing": daily_briefing,
    "project_health": project_health,
    "cross_system_investigation": cross_system_investigation,
    "weekly_digest": weekly_digest,
    "decision_lookup": decision_lookup,
    "decision_get_by_id": decision_get_by_id,
    "oauth_status_check": oauth_status_check,
    "meeting_lookup": meeting_lookup,
    "notes_search_hybrid": notes_search_hybrid,
    "notes_backlinks": notes_backlinks,
    "notes_graph": notes_graph,
    "tags_list": tags_list,
    "tasks_list_all": tasks_list_all,
    "tasks_search_general": tasks_search_general,
    "task_get_single": task_get_single,
    "github_open_prs": github_open_prs,
    "github_issue_search": github_issue_search,
    "github_commit_search": github_commit_search,
    "github_repo_activity": github_repo_activity,
    "github_get_issue_detail": github_get_issue_detail,
    "calendar_today": calendar_today,
    "calendar_week": calendar_week,
    "calendar_find": calendar_find,
    "projects_list_all": projects_list_all,
    "projects_search": projects_search,
    "project_status_check": project_status_check,
    "create_task_without_approval": create_task_without_approval,
    "create_task_full_round_trip": create_task_full_round_trip,
    "update_project_status_without_approval": update_project_status_without_approval,
    "complete_task_without_approval": complete_task_without_approval,
    "tags_rename_without_approval": tags_rename_without_approval,
    "notes_create_without_approval": notes_create_without_approval,
    "calendar_create_event_without_approval": calendar_create_event_without_approval,
    "high_risk_delete_requires_admin_and_approval": high_risk_delete_requires_admin_and_approval,
    "high_risk_delete_admin_without_approval": high_risk_delete_admin_without_approval,
    "malicious_note_summary": malicious_note_summary,
    "malicious_note_follow_instructions": malicious_note_follow_instructions,
}


_SCENARIOS = load_scenarios()


def test_scenario_dataset_has_at_least_30_scenarios() -> None:
    count = len(_SCENARIOS)
    assert count >= 30, f"expected >=30 scenarios per DevBrain_vision.md §26, got {count}"


def test_every_scenario_id_is_unique() -> None:
    ids = [s["id"] for s in _SCENARIOS]
    assert len(ids) == len(set(ids))


def test_every_scenario_has_a_registered_runner() -> None:
    missing = [s["id"] for s in _SCENARIOS if s["entrypoint"] not in RUNNERS]
    assert not missing, f"scenarios with no matching RUNNERS entry: {missing}"


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=lambda s: s["id"])
async def test_scenario(
    scenario: dict[str, Any], monkeypatch: pytest.MonkeyPatch, patched_uow: AsyncSession
) -> None:
    spies = [_install_spy(monkeypatch, target) for target in scenario["expected_calls"]]
    runner = RUNNERS[scenario["entrypoint"]]
    expect_error = scenario.get("expect_error")

    if expect_error:
        error_type = _ERROR_TYPES[expect_error]
        with pytest.raises(error_type):
            await runner(patched_uow)
    else:
        await runner(patched_uow)

    for target, spy in zip(scenario["expected_calls"], spies, strict=True):
        assert spy.calls >= 1, f"{scenario['id']}: expected {target} to be called, it wasn't"
