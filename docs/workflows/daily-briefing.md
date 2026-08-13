# Workflow: Daily Developer Briefing

`DevBrain_vision.md` §27 (Flagship Demo #1). Orchestrator:
`backend/src/devbrain_backend/agents/daily_briefing.py::generate_daily_briefing`.
Read-only — no service call in this workflow ever passes a `role`/
`approval_id`.

## What it gathers

Today's calendar events (`calendar_service.get_today_events`), all tasks
filtered to high-priority open ones and blocked ones
(`tasks_service.list_tasks`), recent decisions and GitHub activity scoped to
whichever projects those tasks touch
(`decisions_service.search_decisions`, `github_activity_for_project`). All
five gathering calls are read-only, low-risk tools.

## Sample request

Via chat (`POST /chat`, keyword-routed — `"daily brief"` / `"daily
briefing"`):

```bash
curl -s http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message": "Give me my daily briefing", "history": []}'
```

Or directly (no HTTP, in-process — this is what the eval suite exercises):

```python
from devbrain_backend.agents.daily_briefing import generate_daily_briefing

result = await generate_daily_briefing()
```

## Sample response shape

```json
{
  "reply": "DAILY DEVELOPER BRIEFING\n\nCalendar\n--------\n10:00 Cost Dashboard...",
  "intent": "daily_briefing",
  "orchestrator": "daily_briefing",
  "data": {
    "calendar_event_count": 2,
    "priority_task_count": 3,
    "blocked_task_count": 1,
    "recent_decision_count": 2,
    "github_activity_count": 4
  }
}
```

`data.briefing_text` (under stub LLM mode) is a deterministic
template-assembled narrative naming the same counts; under `real` mode it's
Claude's synthesis over the identical structured data — see
`docs/architecture/agent-flow.md` for the switch.

## Where this is tested

`backend/tests/unit/test_daily_briefing.py` (mocked services),
`tests/eval/scenarios.json` (`daily_briefing_basic` scenario, asserting the
real orchestrator calls the expected services), `DEMO.md` step 4 (live
manual run).
