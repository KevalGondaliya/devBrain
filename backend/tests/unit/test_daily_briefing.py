"""Unit tests for `daily_briefing` — every service call mocked, LLM client
is a recording fake."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from _llm_fakes import RecordingLLMClient
from devbrain_backend.agents import daily_briefing


@dataclass
class FakeEvent:
    title: str
    starts_at: datetime


@dataclass
class FakeTask:
    id: str
    project_id: str
    title: str
    status: str
    priority: str | None
    due_date: datetime | None = None
    blocked_reason: str | None = None


@dataclass
class FakeProject:
    id: str
    name: str
    status: str = "active"


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

    monkeypatch.setattr(daily_briefing, "github_activity_for_project", fake_github_activity)


async def test_generate_daily_briefing_gathers_and_synthesizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = str(uuid.uuid4())
    event = FakeEvent(title="Standup", starts_at=datetime.now(tz=UTC))
    priority_task = FakeTask(
        id="t1", project_id=project_id, title="Implement OAuth", status="todo", priority="high"
    )
    blocked_task = FakeTask(
        id="t2",
        project_id=project_id,
        title="Fix migration",
        status="blocked",
        priority="medium",
        blocked_reason="Waiting on DB access",
    )
    project = FakeProject(id=project_id, name="MCP Platform")
    decision = FakeDecision(id="d1", title="Use scoped OAuth", decision="Adopt scoped OAuth")

    async def fake_get_today_events() -> list[FakeEvent]:
        return [event]

    async def fake_list_tasks(
        *, project_id: str | None = None, status: str | None = None
    ) -> list[FakeTask]:
        return [priority_task, blocked_task]

    async def fake_get_project(*, project_id: str) -> FakeProject:
        return project

    async def fake_search_decisions(*, query: str, limit: int = 10) -> list[FakeDecision]:
        assert query == "MCP Platform"
        return [decision]

    monkeypatch.setattr(daily_briefing.calendar_service, "get_today_events", fake_get_today_events)
    monkeypatch.setattr(daily_briefing.tasks_service, "list_tasks", fake_list_tasks)
    monkeypatch.setattr(daily_briefing.projects_service, "get_project", fake_get_project)
    monkeypatch.setattr(daily_briefing.decisions_service, "search_decisions", fake_search_decisions)

    llm = RecordingLLMClient(response="STUBBED BRIEFING")
    result = await daily_briefing.generate_daily_briefing(llm=llm)

    assert result.briefing_text == "STUBBED BRIEFING"
    assert result.calendar_event_count == 1
    assert result.priority_task_count == 1
    assert result.blocked_task_count == 1
    assert result.recent_decision_count == 1
    assert result.github_activity_count == 0
    assert len(llm.calls) == 1, "LLM must be called exactly once for the synthesis step"
    prompt = llm.last_prompt
    assert "Implement OAuth" in prompt
    assert "Fix migration" in prompt
    assert "Use scoped OAuth" in prompt


async def test_generate_daily_briefing_defaults_to_get_llm_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No `llm=` kwarg -> uses `get_llm_client()` (stub mode by default),
    proving the orchestrator never hardcodes a concrete LLM class."""

    async def fake_get_today_events() -> list[FakeEvent]:
        return []

    async def fake_list_tasks(
        *, project_id: str | None = None, status: str | None = None
    ) -> list[FakeTask]:
        return []

    monkeypatch.setattr(daily_briefing.calendar_service, "get_today_events", fake_get_today_events)
    monkeypatch.setattr(daily_briefing.tasks_service, "list_tasks", fake_list_tasks)

    result = await daily_briefing.generate_daily_briefing()
    assert result.briefing_text != ""
