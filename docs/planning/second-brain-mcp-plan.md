# Second Brain MCP — Detailed Build Plan (Python)

## 0. Why this project

This single build demonstrates almost every line item in the job post:
- A **custom MCP server** you designed and wrote (not a wrapper around someone else's)
- Clear separation of **tools vs. skills vs. agents/workflows** — an explicit disqualifier if you can't explain this
- Production concerns: **security, layered architecture, Docker, tests, CI**
- Domain fit: this *is* their "Second Brain" (Claude + Obsidian + Notion) infrastructure, modeled directly

---

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Matches your preference; excellent MCP + data-tooling support |
| MCP framework | `mcp` official SDK, using **FastMCP** (high-level, decorator-based) | Official, actively maintained by Anthropic, least boilerplate |
| Validation | Pydantic v2 | FastMCP already uses it for tool schemas — no extra library |
| DB | PostgreSQL 16 + `pgvector` extension | Real relational + vector search in one engine, easy to justify architecturally |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic | Industry standard, demonstrates "clean architecture" not raw SQL scripts |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`), run **locally** | No external API key, no data leaves the box — a genuine security talking point for the interview. Mention Voyage AI as the production-scale swap-in (Anthropic's recommended embeddings partner) |
| Package/env mgmt | `uv` | Fast, modern, single lockfile; falls back to `poetry` if they prefer that in interview |
| Logging | `structlog` | Structured JSON logs — looks production-grade, easy to wire to an audit table |
| Testing | `pytest`, `pytest-asyncio`, `httpx` for transport tests | Standard, fast |
| Lint/type | `ruff` + `mypy` | One tool for lint+format, strict typing shows care |
| Containerization | Docker Compose: `postgres(pgvector)`, `mcp-server`, `adminer` (optional DB browser) | One-command spin-up for the demo |
| CI | GitHub Actions: lint → typecheck → test → build image | Signals real engineering discipline, not just a script |

---

## 2. Project Structure

```
second-brain-mcp/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── pyproject.toml
├── alembic.ini
├── README.md
├── ARCHITECTURE.md              # diagram + tools/skills/agents explainer
├── src/
│   └── second_brain/
│       ├── server.py             # FastMCP entrypoint (transport, auth)
│       ├── config.py             # env-based settings (pydantic-settings)
│       ├── auth.py               # API key / bearer token middleware
│       ├── db/
│       │   ├── models.py         # SQLAlchemy models
│       │   ├── session.py
│       │   └── migrations/       # alembic
│       ├── services/              # business logic, DB-agnostic
│       │   ├── notes_service.py
│       │   ├── links_service.py
│       │   ├── search_service.py  # hybrid keyword + vector search
│       │   └── embeddings.py
│       ├── tools/                 # MCP tool definitions (thin, call services)
│       │   ├── notes_tools.py
│       │   ├── links_tools.py
│       │   └── tag_tools.py
│       ├── resources/             # MCP resources (read-only browsing)
│       │   └── note_resources.py
│       ├── prompts/               # MCP prompt templates
│       │   └── digest_prompts.py
│       ├── agents/                # multi-step orchestrated workflows
│       │   └── weekly_digest_agent.py
│       └── audit.py               # logs every tool call: who/what/when
├── scripts/
│   └── seed_dummy_data.py         # Faker-based synthetic "Second Brain"
└── tests/
    ├── unit/
    └── integration/
```

This layering (`tools` → `services` → `db`) is itself a talking point: tools stay thin and swappable, business logic is testable without MCP or Postgres in the loop.

---

## 3. Data Model

```
notes         id, title, slug, content_md, created_at, updated_at, deleted_at
tags          id, name
note_tags     note_id, tag_id
links         source_note_id, target_note_id, context_snippet   -- [[wikilinks]]
embeddings    note_id, vector(384), model_name, created_at
audit_log     id, tool_name, arguments_json, actor, called_at, duration_ms, status
```

The `audit_log` table is a small addition that pays off disproportionately in an interview — it's exactly what a fractional CTO would ask "how do we govern this?" and you can point at a table.

---

## 4. MCP Surface — the actual demo content

**Tools** (deterministic, single-purpose — callable directly by Claude):
- `notes.create(title, content_md, tags[])`
- `notes.get(id | slug)`
- `notes.update(id, ...)`
- `notes.delete(id)` — soft delete
- `notes.search(query, mode="hybrid"|"keyword"|"semantic", limit)`
- `tags.list()` / `tags.rename(old, new)`
- `links.get_backlinks(note_id)`
- `links.get_graph(note_id, depth=2)` — subgraph traversal, Obsidian-style

**Resources** (read-only, addressable — for browsing without invoking a tool):
- `secondbrain://note/{id}`
- `secondbrain://tag/{name}`

**Prompts** (reusable templates the client can select):
- `summarize-note`
- `weekly-digest`
- `find-related-notes`

**Agent / workflow** (the piece that proves you understand orchestration, not just tool-calling):
- `weekly_digest_agent.py`: pulls notes from the last 7 days → summarizes via Claude → creates a new "digest" note → links it back to source notes → writes an audit entry. This is deliberately built as a standalone orchestrator that *calls the same services the tools call*, so you can explain in the interview: "a tool is one deterministic step; a skill is a documented, reusable instruction bundle (I'll ship one as an actual `SKILL.md`); an agent is what strings tools together with judgment and state across steps — like this digest."

That one paragraph, backed by working code, directly answers their explicit screening bar: *"Deep understanding of AI agents, skills, and workflows — and the differences between them."*

---

## 5. Security (production-mindset checklist)

- Secrets via `.env`, never committed; `.env.example` checked in
- Bearer-token auth middleware on the HTTP/SSE transport (skip only for local stdio dev mode)
- All tool inputs validated via Pydantic schemas — no unvalidated input reaches the DB
- SQLAlchemy ORM (parameterized) — no raw string-built SQL anywhere
- Least-privilege Postgres role for the app (no superuser)
- Rate limiting middleware (simple token-bucket) on the transport
- Full audit log of every tool invocation
- Dependency scanning in CI (`pip-audit` or `uv`'s equivalent)

---

## 6. Dummy Data Strategy

`scripts/seed_dummy_data.py` uses `Faker` to generate ~150 interlinked markdown notes across 5–6 realistic clusters (projects, meeting notes, people, reading notes, ideas), with real `[[wikilinks]]` between them and tag distributions that aren't uniform (so search/graph demos look organic, not obviously synthetic). Embeddings are computed on insert so semantic search works out of the box.

---

## 7. Build Phases (part-time pace, ~10–14 days)

| Phase | Work | Est. |
|---|---|---|
| 0 | Repo scaffold, `uv` project, Docker Compose skeleton, CI skeleton | 1 day |
| 1 | DB models, Alembic migrations, seed script + Faker data | 2 days |
| 2 | Core tools: CRUD + hybrid search | 3 days |
| 3 | Backlinks/graph tools, resources, prompt templates | 2 days |
| 4 | Weekly-digest agent (the tools/skills/agents proof point) | 2 days |
| 5 | Auth, rate limiting, audit log, test suite, CI green | 2 days |
| 6 | README, `ARCHITECTURE.md` with diagram, short demo recording | 1–2 days |

---

## 8. Deliverables Checklist for the Application

- [ ] Public GitHub repo, clean incremental commit history (not one giant commit)
- [ ] `README.md`: what it is, architecture diagram, one-command `docker compose up` setup
- [ ] `ARCHITECTURE.md`: explicit "tools vs. skills vs. agents" section — this is your disqualifier-proofing document
- [ ] `.env.example`, no secrets in history
- [ ] Passing test suite + CI badge in README
- [ ] 3–5 minute screen recording: `docker compose up` → connect Claude Code → create/search notes → trigger digest agent → show audit log
- [ ] One paragraph in your application linking each JD bullet to a specific file/feature

---

## 9. Interview Demo Script

1. `docker compose up` from a clean clone — everything comes up
2. Connect Claude Code/Desktop to the server over stdio or HTTP
3. Live: create a note, search hybrid, pull backlinks graph for a note
4. Trigger `weekly_digest_agent` — show it calling multiple tools with state, not just one function
5. Show the audit log table — "this is how you'd govern MCP rollout across the stack"
6. Show `pytest` green and the CI run
