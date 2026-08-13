# MCP tool design

## Tools vs. resources vs. prompts

MCP defines three distinct primitives; DevBrain uses all three, on purpose,
for different jobs:

- **Tools** (`@mcp.tool()`) — invokable capabilities with validated input and
  a structured result. Everything that reads or writes data in DevBrain is a
  tool: `notes.search`, `create_task`, `get_today_events`, etc. 34 of them
  across five servers (`docs/mcp/overview.md`).
- **Resources** (`@mcp.resource()`) — addressable, read-only content a
  client can fetch by URI without "calling" anything, for browsing rather
  than querying. Knowledge MCP exposes `secondbrain://note/{id}` and
  `secondbrain://tag/{name}`
  (`services/knowledge_mcp/src/knowledge_mcp/resources/`). Only Knowledge
  MCP has resources — the other four servers' data (tasks, projects,
  calendar events) is more naturally query-shaped (search/filter) than
  browse-by-fixed-id-shaped, so a resource wasn't a fit there.
- **Prompts** (`@mcp.prompt()`) — reusable prompt *templates* a client can
  select, not orchestration logic themselves. Knowledge MCP registers
  `summarize-note`, `weekly-digest`, `find-related-notes`
  (`services/knowledge_mcp/src/knowledge_mcp/prompts/digest_prompts.py`) —
  registration only; the actual multi-step orchestration behind
  `weekly-digest` lives in `backend/agents/weekly_digest.py`, deliberately
  kept out of the MCP server itself (see `ARCHITECTURE.md` §1's
  "the one place all three meet").

## The "no `execute_sql`" rule

`docs/planning/DevBrain_vision.md` §23, `ORCHESTRATION.md` §1: **no tool
ever exposes raw or dynamic SQL.** Every tool exposes a named business
capability (`search_tasks`, `update_project_status`) backed by parameterized
SQLAlchemy ORM queries confined to a `repositories/` module — never a
free-text query parameter that reaches the database. This is checked, not
just declared: grep any service's `repositories/*.py` and every query is
built with SQLAlchemy's expression language (`select()`, `.where()`, ORM
attribute comparisons); nothing constructs a SQL string. `notes.search`'s
`mode="hybrid"|"keyword"|"semantic"` parameter is the closest DevBrain gets
to "flexible querying," and even that is a fixed enum dispatching to three
pre-written query shapes in `search_service.py`, not arbitrary user-supplied
predicates.

## Every tool input is a Pydantic model / type-validated

FastMCP builds each tool's client-visible JSON schema from its Python
function's type hints and `pydantic.Field` constraints — e.g.
`title: Annotated[str, Field(min_length=1, max_length=300)]` in
`create_task` (`services/task_mcp/src/task_mcp/tools/tasks_tools.py`). No
tool body accepts an unvalidated `dict`; malformed input is rejected before
the function runs at all. `tests/security/test_malicious_arguments.py`
(this phase) proves this directly — oversized strings, wrong types, and
out-of-range values are all rejected by the tool's own Pydantic layer, not
by defensive code inside the service.

## Risk tiers

Every tool is classified low / medium / high in its own service's `risk.py`
(`packages/common/src/devbrain_common/risk.py`'s `make_risk_lookup` factory
provides the shared plumbing; each service supplies its own tool→tier
table, since the tier is genuinely service-specific):

| Tier | Meaning | Gate | Examples |
|---|---|---|---|
| **Low** | Read-only | `Role.VIEWER` minimum, no approval | `notes.search`, `get_task`, `list_projects`, all of GitHub MCP |
| **Medium** | Routine write | `Role.USER` minimum + `enforce_approval` (admin bypasses, audited) | `create_task`, `update_task`, `complete_task`, `update_project_status`, `create_event`, `notes.create`, `notes.update`, `tags.rename` |
| **High** | Destructive/bulk | `Role.ADMIN` minimum **and** a valid approval — admin status alone does not bypass | `notes.delete` (the one high-risk tool in the current tool set) |

This exactly mirrors `DevBrain_vision.md` §10's low/medium/high policy, with
one resolved ambiguity: §10 phrases high risk as "strong approval **or**
admin-only," which read alone could mean either gate suffices. §12's worked
authorization matrix (`delete_task`/`bulk_update` both listed `Admin: Yes`
**and** `Approval: Yes`) resolves it as *both required together* — the
design DevBrain implements for `notes.delete`
(`services/knowledge_mcp/src/knowledge_mcp/services/notes_service.py::_enforce_high_risk_approval`).
Full mechanics, including exactly what `arguments` dict each gated tool
matches an approval against: `docs/mcp/security.md` and
`PROGRESS_REPORT.md`'s Phase 6 "Decisions made".

## Structured errors

Every tool wraps its body in `handle_tool_errors`
(`packages/common/src/devbrain_common/mcp_tooling.py`): any
`DevBrainError` subclass renders as `{"error": {"code", "message"}}`; any
other exception is caught and rendered as a generic `internal_error`
envelope — a raw Python traceback or stack string never reaches an MCP
client. The same decorator enforces a per-call timeout
(`Settings.tool_timeout_seconds`, default 30s) via `asyncio.wait_for`,
raising `UpstreamTimeoutError` (504) on expiry. Error taxonomy:
`docs/mcp/security.md`.
