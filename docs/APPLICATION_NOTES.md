# APPLICATION_NOTES.md

A drafting aid for the actual job application — not a code artifact. One
line per job-posting bullet, mapped to the specific file/feature in this
repo that answers it. Source framing:
`docs/planning/second-brain-mcp-plan.md` §0 ("Why this project" — the
job-post bullets this build was designed against) plus the fuller bullet set
this repo was scoped to cover.

| Job posting bullet | Answered by |
|---|---|
| MCP server integrations / rollout across a real stack | Five independent, production-shaped MCP servers (`services/knowledge_mcp`, `project_mcp`, `task_mcp`, `github_mcp`, `calendar_mcp`), each its own deployable service with its own Dockerfile — `docs/mcp/overview.md`, `ARCHITECTURE.md` §2 |
| Deep understanding of tools, skills, and agents/workflows, and the differences between them | `ARCHITECTURE.md` §1 — one real MCP tool, one real `SKILL.md`, one real multi-step orchestrator, quoted directly, with the one place all three interlock (`weekly_digest`) called out explicitly |
| Claude Code / Claude Desktop experience | `DEMO.md` — connecting a real Claude Desktop/Code client over stdio or HTTP to any of the five servers and driving the flagship demos live; this entire repo was built session-by-session with Claude Code as the primary tool (`ORCHESTRATION.md`, `PROGRESS_REPORT.md`) |
| Distributed systems / APIs | Five independently-runnable services sharing one Postgres schema behind a FastAPI HTTP surface, each with its own risk/auth/audit boundary — `docs/architecture/system.md`; idempotency for safe retries, rate limiting, structured cross-service error handling — `docs/mcp/security.md` |
| Obsidian-as-AI-workspace / "Second Brain" domain fit | Knowledge MCP is modeled directly on Obsidian's own primitives — `[[wikilinks]]` resolved to real backlink/graph traversal, hybrid keyword+semantic note search, tag rename with cascade — `services/knowledge_mcp/README.md`; `ROADMAP.md` §1 covers the real-vault-sync extension |
| Production architecture (security, layering, Docker, tests, CI) | Fixed `tool → service → repository/adapter → Postgres` layering enforced identically across all five servers, human-in-the-loop approval gate, full audit trail, Docker Compose for the whole stack, CI (lint → typecheck → test → build) — `ARCHITECTURE.md`, `SECURITY.md`, `.github/workflows/ci.yml` |
| Testing discipline / quality bar | Unit, integration, security, e2e, and an evaluation-scenario suite, all passing — `tests/`, `PROGRESS_REPORT.md`'s running test-count history (444+ before this phase) |
| Human-in-the-loop / safe AI action design | The full propose → approve → execute → audit approval gate, with a dedicated high-risk (admin **and** approval) tier for destructive actions — `docs/mcp/tool-design.md`'s risk-tier table, `docs/workflows/task-management.md` |
| Prompt-injection / adversarial-input awareness | A seeded malicious note fixture, a skill-level safety rule, prompt-construction quarantine of untrusted content, and the structural guarantee that no LLM output is ever load-bearing for a tool call — `docs/mcp/security.md`'s prompt-injection section |
