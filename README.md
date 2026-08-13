# DevBrain

A Claude-powered developer command center: five production-shaped MCP
servers (Knowledge, Project, Task, GitHub, Calendar) over synthetic data, a
FastAPI backend, and a Next.js frontend — a portfolio build demonstrating
real MCP server design, the tools/skills/agents distinction, and production
concerns (layered architecture, auth, audit, human-in-the-loop approvals,
Docker, tests, CI).

<!-- TODO: CI badge once pushed to GitHub -->

## What it is

Claude gets a controlled, auditable window into a developer's world —
projects, tasks, meetings, decisions, notes, GitHub activity, calendar — and
can reason across all of it and safely propose actions, never execute one on
its own authority. See `ARCHITECTURE.md` for the full system design and the
concrete tool/skill/agent breakdown; `docs/planning/` for the two source
specs this build follows.

## Quickstart

```bash
git clone <repo-url> && cd devbrain
cp .env.example .env
docker compose up -d
.venv/bin/python scripts/generate_all.py --size default --seed 42 --truncate
open http://localhost:3000   # frontend
curl http://localhost:8000/health   # backend
```

Full walkthrough — connecting Claude Desktop/Code, triggering an agent
workflow, approving a gated write, reading the audit log:
**[`DEMO.md`](./DEMO.md)**.

## Links

| | |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System design, the tools/skills/agents explainer with real code |
| [`DEMO.md`](./DEMO.md) | 5-minute interview/demo script, exact commands |
| [`SECURITY.md`](./SECURITY.md) | Security posture summary |
| [`DEVELOPMENT.md`](./DEVELOPMENT.md) | How to work on this repo, run tests, migrations |
| [`ROADMAP.md`](./ROADMAP.md) | What's next if this engagement continues |
| [`docs/`](./docs/) | Deep dives: architecture, MCP design, workflows |
| [`PROGRESS_REPORT.md`](./PROGRESS_REPORT.md) | Living build log — what's done, decisions, resume points |

## Status

All ten build phases complete (`PROGRESS_REPORT.md`'s Overall status line
tracks this precisely). Test suite: **444+ passing**
(`tests packages services backend scripts` at repo root, plus `tests/eval`,
`tests/security`, `tests/e2e` — see `PROGRESS_REPORT.md`'s Phase 10 section
for the exact current count) — `ruff check`/`format` and `mypy --strict`
clean across every source tree.

## Origin

This project's design comes from two source documents, kept for reference in
[`docs/planning/`](./docs/planning/):
- [`second-brain-mcp-plan.md`](./docs/planning/second-brain-mcp-plan.md) — the
  detailed spec adopted wholesale for the Knowledge MCP server
- [`DevBrain_vision.md`](./docs/planning/DevBrain_vision.md) — the full
  multi-server architecture and phase-by-phase build order

`ORCHESTRATION.md` documents how this was actually built (phase protocol,
golden rules, QA loop) — itself part of the portfolio story: this repo's
incremental commit history is a deliverable, not an afterthought.

## Architecture, in one line

`MCP tool` (thin, validated) → `service` (business logic, DB-agnostic) →
`repository/adapter` (Postgres or external API) → `Postgres`, with auth,
risk-tiered approval gating, and audit logging enforced identically at every
layer across all five servers. Full diagram: `ARCHITECTURE.md` §2.
