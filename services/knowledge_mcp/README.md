# Knowledge MCP

DevBrain's flagship MCP server: notes (CRUD + hybrid keyword/semantic
search), tags, wikilink backlinks/graph, and read access to meetings and
decisions. Spec: `docs/planning/second-brain-mcp-plan.md` §2–§6 +
`docs/planning/DevBrain_vision.md` §11.1.

## Layering

```
tools/          FastMCP @mcp.tool() functions — thin, type-hint/Pydantic
                validated, role-checked, one service call, one return.
services/       Business logic: hybrid-search ranking, backlink/graph BFS,
                tag-rename cascading, wikilink parsing. DB-agnostic enough
                to unit test by mocking repositories/.
repositories/   SQLAlchemy ORM queries only. Only unit_of_work.py imports
                devbrain_common.db directly.
resources/      secondbrain://note/{id}, secondbrain://tag/{name}
prompts/        summarize-note, weekly-digest, find-related-notes templates
skills/         summarize-note/SKILL.md
```

## Tool vs. skill vs. agent — this project's explicit disqualifier-proofing

`second-brain-mcp-plan.md` §0 calls this out as a screening bar to answer
directly, so here it is with pointers to the actual files:

- **Tool** — one deterministic, single-purpose call with a fixed
  input/output contract. Example: `notes.get` in
  [`src/knowledge_mcp/tools/notes_tools.py`](src/knowledge_mcp/tools/notes_tools.py) —
  give it an id, it returns that note or a structured error. No judgment,
  no state across calls.
- **Skill** — a documented, reusable *instruction bundle* a model follows
  when the situation calls for judgment, but that isn't itself a single
  API call. Example:
  [`src/knowledge_mcp/skills/summarize-note/SKILL.md`](src/knowledge_mcp/skills/summarize-note/SKILL.md) —
  frontmatter + steps + a safety rule + an output format for turning one
  note's content into a faithful summary. It's invoked the same way every
  time (directly, via the `summarize-note` MCP prompt, or as a step inside
  a larger workflow) but it isn't a function signature — it's judgment
  applied consistently.
- **Agent / workflow** — multi-step orchestration *with state* across
  steps, calling multiple tools (and skills) in sequence, making decisions
  about what to do next based on what came back. This server does **not**
  build one — the `weekly-digest` MCP *prompt* registered in
  [`src/knowledge_mcp/prompts/digest_prompts.py`](src/knowledge_mcp/prompts/digest_prompts.py)
  is only the template describing the steps; the actual orchestrator that
  executes them (search recent notes -> summarize each cluster -> create a
  digest note -> link it back to sources -> write the audit entry) is
  Phase 7's `weekly_digest` agent under `backend/src/devbrain_backend/agents/`
  (see `PROGRESS_REPORT.md` Phase 7), built on top of the same services
  this server exposes as tools. Keeping that orchestrator out of this
  server is deliberate: tools/skills stay swappable and independently
  testable; the agent is a separate consumer of them, not baked into the
  MCP surface itself.

## Security

Every tool input is validated by FastMCP from type hints/`pydantic.Field`
constraints (`src/knowledge_mcp/tools/*.py`) — no hand-rolled validation.
Every tool resolves the caller's role via
[`src/knowledge_mcp/auth.py`](src/knowledge_mcp/auth.py)
(`devbrain_common.auth` primitives: `Role`, `TokenStore`, `check_role`) and
enforces a minimum role before calling any service — `Role.VIEWER` for
reads, `Role.USER` for writes. Every write calls
`devbrain_common.audit.record_audit_event` inside the same transaction as
its data change. No raw SQL anywhere (SQLAlchemy ORM only, confined to
`repositories/`). Note `content` is always treated as data, never
instructions — see the security note atop
`src/knowledge_mcp/services/notes_service.py` and the safety rule in the
`summarize-note` skill above.

## Running locally

```bash
# stdio (local Claude Desktop/Code dev connection)
.venv/bin/python -m knowledge_mcp.server

# HTTP (bearer auth enforced per-tool; set MCP_API_TOKENS in .env)
KNOWLEDGE_MCP_TRANSPORT=streamable-http .venv/bin/python -m knowledge_mcp.server
```
