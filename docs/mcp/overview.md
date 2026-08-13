# MCP servers overview

DevBrain runs five independent MCP servers, each its own `uv` workspace
package under `services/`, each following the same
`tools → services → repositories/adapters` layering (`ORCHESTRATION.md` §1).
Every server also mounts the same 3 shared approval tools
(`packages/common/src/devbrain_common/approval_tools.py`:
`request_approval`, `list_pending_approvals`, `decide_approval`) since they
all point at the same Postgres `approvals` table — deliberately not a sixth
"approvals" server.

| Server | Port | Tools (own) | Owns | Transport |
|---|---|---|---|---|
| **Knowledge MCP** | 8001 | 13 | Notes (CRUD + hybrid keyword/semantic search), tags, wikilink backlinks/graph, read access to meetings and decisions. The flagship — `docs/planning/second-brain-mcp-plan.md`'s whole design. | stdio / streamable-http |
| **Project MCP** | 8002 | 5 | Project listing/search/get, status read + update. | stdio / streamable-http |
| **Task MCP** | 8003 | 6 | Task listing/search/get/create/update/complete, idempotent creates. | stdio / streamable-http |
| **GitHub MCP** | 8004 | 6 | Issues, PRs, commits, repository activity — all read-only, backed by an adapter `Protocol` (fake data today, real GitHub API later). | stdio / streamable-http |
| **Calendar MCP** | 8005 | 4 | Today/week events, find, create — same adapter `Protocol` pattern as GitHub. | stdio / streamable-http |

34 tools total across the five servers, plus the 3 shared approval tools
mounted identically on each (37 tool registrations per-server-sum, 34+3
distinct tool names). Exact list, verified by grepping every service's
`tools/*.py` for `@mcp.tool(name=...)`:

- **Knowledge MCP**: `notes.create`, `notes.get`, `notes.update`,
  `notes.delete`, `notes.search`, `tags.list`, `tags.rename`,
  `links.get_backlinks`, `links.get_graph`, `search_meetings`,
  `read_meeting`, `search_decisions`, `get_decision`.
- **Project MCP**: `list_projects`, `search_projects`, `get_project`,
  `get_project_status`, `update_project_status`.
- **Task MCP**: `list_tasks`, `search_tasks`, `get_task`, `create_task`,
  `update_task`, `complete_task`.
- **GitHub MCP**: `search_issues`, `get_issue`, `list_pull_requests`,
  `get_pull_request`, `search_commits`, `get_repository_activity`.
- **Calendar MCP**: `get_today_events`, `get_week_events`, `find_event`,
  `create_event`.

Every server also exposes:

- **Resources** (Knowledge MCP only) — `secondbrain://note/{id}`,
  `secondbrain://tag/{name}` (`services/knowledge_mcp/src/knowledge_mcp/resources/`).
- **Prompts** (Knowledge MCP only) — `summarize-note`, `weekly-digest`,
  `find-related-notes` (`services/knowledge_mcp/src/knowledge_mcp/prompts/digest_prompts.py`).
- **A `risk.py`** classifying every tool low/medium/high
  (`docs/mcp/tool-design.md` has the full rule set + current tier table).

## Live introspection

`GET /tools` and `GET /permissions` on the FastAPI backend
(`backend/src/devbrain_backend/api/introspection.py`) build this same table
*programmatically* — real `create_server()` + `await mcp.list_tools()` per
service, plus each service's own `risk.py` — rather than a hand-maintained
copy. That endpoint is the single source of truth if this document ever
drifts from the code; this document is the narrative version for a reader
who wants the "why," not a live JSON dump.

## Adapter seam (GitHub MCP, Calendar MCP)

Both services insert an `adapters/` layer between `services/` and the data
source: `adapters/protocol.py` defines a `typing.Protocol`
(`GithubAdapter`/`CalendarAdapter`) plus a frozen-dataclass "Record" return
shape; `adapters/fake_*.py` implements it over the existing
Postgres-seeded repository; `adapters/real_*.py` is a same-signature stub
whose every method raises `NotImplementedError` pointing at exactly where a
real vendor client plugs in. The service layer imports only the Protocol,
never a concrete adapter class, except in the one `get_adapter()` factory
function — see `docs/planning/DevBrain_vision.md` §21 and
`PROGRESS_REPORT.md`'s Phase 5 "Decisions made" for the full design and how
it's proven real (a hand-rolled test double, independent of `fake_*.py`,
passes the same service tests). `ROADMAP.md` covers what swapping in the
real GitHub/Google Calendar APIs would take.

## Running a server directly

```bash
# stdio (Claude Desktop/Code local dev connection)
cd services/knowledge_mcp && ../../.venv/bin/python -m knowledge_mcp.server

# HTTP (bearer auth enforced per-tool; MCP_API_TOKENS in .env)
KNOWLEDGE_MCP_TRANSPORT=streamable-http ../../.venv/bin/python -m knowledge_mcp.server
```

Same pattern for `project_mcp`, `task_mcp`, `github_mcp`, `calendar_mcp` —
swap the module name and the corresponding `.env` `*_MCP_TRANSPORT` var. See
`DEMO.md` for connecting a real Claude Desktop/Code client.
