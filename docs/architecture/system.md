# System architecture

The detailed version of `ARCHITECTURE.md` §2's diagram, with component
responsibilities spelled out. Read `ARCHITECTURE.md` first if you haven't —
this expands on it, it doesn't replace it.

## Diagram

```
                                    USER
                                     |
                    +----------------+----------------+
                    |                                 |
                    v                                 v
          +--------------------+            Claude Desktop / Code
          |     Next.js         |            connects directly over
          |  frontend/app/*      |            MCP (stdio locally, or
          |  chat/projects/       |            streamable-http per
          |  activity/tools/       |            server) — bypasses
          |  permissions           |            backend entirely
          +----------+-----------+
                     | HTTP, bearer token
                     v
          +------------------------+
          |     FastAPI backend      |
          |  backend/src/devbrain_    |
          |  backend/api/             |
          |  main.py, auth.py,        |
          |  introspection.py,        |
          |  routers/*.py             |
          +------------+-------------+
                       |
                       | in-process function calls into
                       | services/*.py (5 services) and
                       | backend/agents/*.py — no MCP hop
                       v
     +---------------------------------------------------+
     |     backend/src/devbrain_backend/agents/            |
     |  daily_briefing · project_health · weekly_digest      |
     |  cross_system_investigation · safe_write                |
     |  (each calls devbrain_common.llm.get_llm_client() for    |
     |   the stub/real-Anthropic synthesis step — agent-flow.md) |
     +----------------------+------------------------------+
                             |
      +----------------------+----------------------+----------------+----------------+
      |                      |                       |                |                |
      v                      v                       v                v                v
+-----------+         +-----------+           +-----------+    +-----------+    +-----------+
|Knowledge  |         | Project   |           |  Task     |    | GitHub    |    | Calendar  |
| MCP :8001 |         | MCP :8002 |           | MCP :8003 |    | MCP :8004 |    | MCP :8005 |
+-----+-----+         +-----+-----+           +-----+-----+    +-----+-----+    +-----+-----+
      |                     |                       |                |                |
   tools/                tools/                  tools/           tools/           tools/
  (13 tools:            (5 tools)               (6 tools)        (6 tools,        (4 tools:
   notes.*, tags.*,                                                all read-        3 read,
   links.*, meetings,                                               only)           1 write)
   decisions)
      |                     |                       |                |                |
      v                     v                       v                v                v
   services/             services/               services/        services/        services/
  (hybrid search,        (status                  (idempotent      (github_         (idempotent
   backlink/graph BFS,     transitions)             create,          service.py)      create,
   tag-rename cascade)                               approval                          approval
                                                       gate)                             gate)
      |                     |                       |                |                |
      v                     v                       v                v                v
  repositories/         repositories/           repositories/    adapters/        adapters/
 (SQLAlchemy ORM        (SQLAlchemy ORM         (SQLAlchemy ORM   protocol.py +    protocol.py +
  only)                  only)                   only)            fake_github.py   fake_calendar.py
                                                                    (wraps a         (wraps a
                                                                    repository)      repository) +
                                                                    real_github.py   real_calendar.py
                                                                    (NotImplemented  (NotImplemented
                                                                    stub, same       stub, same
                                                                    signatures)      signatures)
      |                     |                       |                |                |
      +---------------------+-----------------------+----------------+----------------+
                             |
                             v
                    PostgreSQL 16 + pgvector
     14 tables: projects, tasks, meetings, decisions, notes, tags,
     note_tags, links, embeddings, github_activities, calendar_events,
     users, audit_logs, approvals
     (packages/common/src/devbrain_common/models.py — one shared schema,
      one shared Alembic migration history, all five services + backend
      connect to the same database via devbrain_common.db.session_scope())
```

Cross-cutting concerns — auth, rate limiting, risk tiers, the approval gate,
audit logging, structured errors — are not a separate box in this diagram
because they aren't a separate service; they're `packages/common` modules
that every tool/service layer above calls directly at the point of use (see
`docs/mcp/security.md` for exactly which module does what).

## Component responsibilities

| Component | Responsible for | Not responsible for |
|---|---|---|
| **Next.js frontend** (`frontend/`) | Rendering 5 pages against the backend's HTTP contract; holding the bearer token client-side | Any business logic, any direct DB/service access |
| **FastAPI backend** (`backend/api/`) | HTTP auth adapter, `/chat` keyword-routing to the 5 agents, read endpoints (`/projects`, `/activity`, `/tools`, `/permissions`), the `/approvals` HTTP path | Reimplementing service logic — every route calls an existing `services/*.py` or `agents/*.py` function |
| **Agents** (`backend/agents/`) | Multi-step orchestration across services, LLM synthesis via the pluggable client, the human-approval proposal/execute two-step for writes | Bypassing the approval gate, authoring tool-call arguments from free text, direct DB/repository access |
| **MCP tool layer** (`services/*/tools/`) | Schema validation (via type hints + `pydantic.Field`), role check (`require_min_role`), exactly one service call, error-envelope translation | Business logic, DB access, holding a session |
| **Service layer** (`services/*/services/`) | Business rules, the approval gate call, idempotency, audit-log writes, DTO construction | Knowing about MCP `Context`, HTTP, or any transport concern |
| **Repository/adapter layer** (`services/*/repositories/`, `services/{github,calendar}_mcp/adapters/`) | Parameterized SQLAlchemy ORM queries; for GitHub/Calendar, a `Protocol` seam so a real vendor API can swap in later without touching the service | Any business logic or validation |
| **`packages/common`** | Shared schema (`models.py`), DB session factory, auth/risk/approval/audit/rate-limit/error/LLM primitives every service and the backend build on | Anything service-specific (each service keeps its own `risk.py` tool→tier table) |
| **PostgreSQL + pgvector** | Durable storage, one schema shared by all five services + backend, vector similarity search for hybrid note search | Business rules, authorization decisions |

## Ports and processes

Five independent MCP server processes (8001–8005), one FastAPI backend
process (8000), one Next.js process (3000), one Postgres instance — all
wired in `docker-compose.yml` (owned by the infra track of Phase 10, not
this document). Every MCP server is independently runnable over stdio for a
direct Claude Desktop/Code connection, or over `streamable-http` for the
backend/frontend's own use — see each service's `README.md` (Knowledge MCP's
is the fullest) and `.env.example`'s per-service `*_MCP_TRANSPORT` vars.
