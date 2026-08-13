"""Unit tests for `project_health` — pure `compute_verdict` plus the full
wired-up orchestrator with every service call mocked."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from _llm_fakes import RecordingLLMClient
from devbrain_backend.agents import project_health


class TestComputeVerdict:
    def test_blocked_when_project_status_is_blocked(self) -> None:
        verdict = project_health.compute_verdict(
            project_status="blocked", blocked_task_count=0, overdue_task_count=0
        )
        assert verdict == "BLOCKED"

    def test_blocked_when_any_task_is_blocked(self) -> None:
        verdict = project_health.compute_verdict(
            project_status="active", blocked_task_count=1, overdue_task_count=0
        )
        assert verdict == "BLOCKED"

    def test_at_risk_when_overdue_but_not_blocked(self) -> None:
        verdict = project_health.compute_verdict(
            project_status="active", blocked_task_count=0, overdue_task_count=2
        )
        assert verdict == "AT_RISK"

    def test_on_track_otherwise(self) -> None:
        verdict = project_health.compute_verdict(
            project_status="active", blocked_task_count=0, overdue_task_count=0
        )
        assert verdict == "ON_TRACK"

    def test_verdict_is_pure_no_llm_involved(self) -> None:
        """Same inputs -> same output, with zero I/O — this is what makes
        the verdict identical regardless of DEVBRAIN_LLM_MODE."""
        kwargs = {"project_status": "active", "blocked_task_count": 0, "overdue_task_count": 1}
        assert project_health.compute_verdict(**kwargs) == project_health.compute_verdict(**kwargs)


@dataclass
class FakeProject:
    id: str
    name: str
    status: str = "active"


@dataclass
class FakeTask:
    id: str
    project_id: str
    title: str
    status: str
    priority: str | None = None
    due_date: datetime | None = None
    blocked_reason: str | None = None


@dataclass
class FakeMeeting:
    id: str
    title: str
    date: str


@dataclass
class FakeDecision:
    id: str
    title: str
    decision: str


@pytest.fixture(autouse=True)
def _no_github_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_github_activity(
        project_name: str, *, pr_limit: int = 5, issue_limit: int = 5
    ) -> list[object]:
        return []

    monkeypatch.setattr(project_health, "github_activity_for_project", fake_github_activity)


async def test_analyze_project_health_blocked_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    project = FakeProject(id="p1", name="MCP Platform", status="active")
    blocked_task = FakeTask(
        id="t1",
        project_id="p1",
        title="OAuth architecture",
        status="blocked",
        blocked_reason="Authentication architecture unresolved",
    )

    async def fake_get_project(*, project_id: str) -> FakeProject:
        return project

    async def fake_list_tasks(
        *, project_id: str | None = None, status: str | None = None
    ) -> list[FakeTask]:
        return [blocked_task]

    async def fake_search_meetings(*, query: str, limit: int = 10) -> list[FakeMeeting]:
        return [FakeMeeting(id="m1", title="Architecture review", date="2026-08-01")]

    async def fake_search_decisions(*, query: str, limit: int = 10) -> list[FakeDecision]:
        return [FakeDecision(id="d1", title="Use scoped OAuth", decision="Adopt it")]

    monkeypatch.setattr(project_health.projects_service, "get_project", fake_get_project)
    monkeypatch.setattr(project_health.tasks_service, "list_tasks", fake_list_tasks)
    monkeypatch.setattr(project_health.meetings_service, "search_meetings", fake_search_meetings)
    monkeypatch.setattr(project_health.decisions_service, "search_decisions", fake_search_decisions)

    llm = RecordingLLMClient(response="Reasons: blocked. Recommendations: unblock it.")
    result = await project_health.analyze_project_health(project_id="p1", llm=llm)

    assert result.verdict == "BLOCKED"
    assert result.blocked_task_count == 1
    assert result.narrative == "Reasons: blocked. Recommendations: unblock it."
    assert "Authentication architecture unresolved" in llm.last_prompt
    assert '"verdict": "BLOCKED"' in llm.last_prompt


async def test_analyze_project_health_at_risk_from_overdue_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = FakeProject(id="p1", name="MCP Platform", status="active")
    overdue_task = FakeTask(
        id="t1",
        project_id="p1",
        title="Write tests",
        status="todo",
        due_date=datetime.now(tz=UTC) - timedelta(days=3),
    )

    async def fake_get_project(*, project_id: str) -> FakeProject:
        return project

    async def fake_list_tasks(
        *, project_id: str | None = None, status: str | None = None
    ) -> list[FakeTask]:
        return [overdue_task]

    async def fake_search_meetings(*, query: str, limit: int = 10) -> list[FakeMeeting]:
        return []

    async def fake_search_decisions(*, query: str, limit: int = 10) -> list[FakeDecision]:
        return []

    monkeypatch.setattr(project_health.projects_service, "get_project", fake_get_project)
    monkeypatch.setattr(project_health.tasks_service, "list_tasks", fake_list_tasks)
    monkeypatch.setattr(project_health.meetings_service, "search_meetings", fake_search_meetings)
    monkeypatch.setattr(project_health.decisions_service, "search_decisions", fake_search_decisions)

    result = await project_health.analyze_project_health(project_id="p1", llm=RecordingLLMClient())

    assert result.verdict == "AT_RISK"
    assert result.overdue_task_count == 1
    assert result.blocked_task_count == 0
