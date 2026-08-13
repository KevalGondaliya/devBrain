# Workflow: Project Analysis

Covers two related orchestrators sharing one theme — "what's going on with
this project, and why":

## Project Health (`DevBrain_vision.md` §29/§10)

`backend/src/devbrain_backend/agents/project_health.py::analyze_project_health`.
Read-only. `compute_verdict` is a **pure, deterministic function** — no LLM
call — so `ON_TRACK`/`AT_RISK`/`BLOCKED` is identical in `stub` and `real`
LLM mode: `BLOCKED` if the project itself is blocked or has any blocked
task, else `AT_RISK` if anything is overdue, else `ON_TRACK`. The LLM client
only writes the narrative "Reasons"/"Recommendations" *for* that
already-decided verdict — matching `DevBrain_vision.md` §10's "the AI should
never be the final authorization authority" posture, extended here to "never
the final health-classification authority" either.

### Sample request/response

```bash
curl -s http://localhost:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the health of the MCP Server project?", "history": []}'
```

```json
{
  "reply": "This project is BLOCKED. The authentication architecture task...",
  "intent": "project_health",
  "orchestrator": "project_health",
  "data": {"verdict": "BLOCKED", "blocked_task_count": 1, "overdue_task_count": 0, ...}
}
```

`/chat`'s project-scoping is a first-match, exact-substring project-name
match (documented limitation — `chat_router.py`'s docstring); the direct
Python call (`analyze_project_health(project_id=...)`) takes a real id and
has no such ambiguity.

## Cross-System Investigation (`DevBrain_vision.md` §7/§8/§29, the flagship demo)

`backend/src/devbrain_backend/agents/cross_system_investigation.py::investigate_project_blockage`.
Chains Project MCP → Task MCP → Knowledge MCP → GitHub MCP exactly per §8's
diagram, then synthesizes one answer that explicitly cites which system each
fact came from (`"Project MCP shows..."`, `"Task MCP shows..."`, etc.).

### Sample request/response

```bash
curl -s http://localhost:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Why is the MCP Server project blocked?", "history": []}'
```

```json
{
  "reply": "Project MCP shows the MCP Server project is blocked. Task MCP shows an open OAuth task. Knowledge MCP surfaces a decision requiring scoped OAuth. GitHub shows PR #48 with two failing tests. Recommendation: resolve the OAuth PR's failing tests before proceeding.",
  "intent": "cross_system_investigation",
  "orchestrator": "cross_system_investigation",
  "data": {"blocked_task_count": 1, "relevant_decision_count": 1, "relevant_meeting_count": 0, "github_activity_count": 2}
}
```

## Where this is tested

`backend/tests/unit/test_project_health.py` (mocked, including
`compute_verdict`'s pure-function branches), `backend/tests/api/test_chat_endpoint.py`
(routing + role gating), `tests/eval/scenarios.json`
(`project_blocked_investigation`, `db_choice_decision` scenarios), `DEMO.md`
step 4.
