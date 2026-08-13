# ROADMAP.md

DevBrain today is a complete, tested, security-conscious portfolio build
over synthetic data. This file is the fuller multi-week vision from
`docs/planning/DevBrain_vision.md` §24 ("Real Integrations") and §32
("Production Target Architecture"), framed explicitly as **what's next if
this engagement continues** — the same "MCP rollout across a real stack"
language the original job posting itself uses. Nothing below is required
for the current build to be complete; it's the deliberate next-phase
scoping.

## 1. Real external integrations (replace the fake adapters)

GitHub MCP and Calendar MCP already have the seam for this —
`adapters/protocol.py`'s `Protocol` + Record types, `adapters/real_*.py`'s
same-signature `NotImplementedError` stubs pointing exactly at where a real
client plugs in (`docs/mcp/overview.md`). The work here is filling those
stubs in, not redesigning anything:

- **GitHub MCP** → real GitHub REST/GraphQL API via a scoped personal access
  token or GitHub App installation token. Needs: OAuth or PAT-based auth,
  rate-limit-aware pagination (GitHub's own 5000 req/hr limit, on top of
  DevBrain's own per-actor limiter), and mapping GitHub's actual issue/PR/
  commit JSON shapes onto `GithubActivityRecord` (currently a straight
  ORM-row translation in `fake_github.py`).
- **Calendar MCP** → Google Calendar API (or Microsoft Graph, given
  `DevBrain_vision.md` §36 mentions both). Needs: OAuth2 with offline
  refresh tokens (stored where? — a new `oauth_tokens` table, not `.env`),
  webhook/push-notification support if events should stay live rather than
  polled, and timezone handling (`CalendarEventRecord`'s `starts_at`/
  `ends_at` are naive-of-source-timezone today, since fake data is generated
  in UTC directly).
- **Knowledge MCP** → optionally, real Obsidian vault sync (the domain this
  whole project is modeled on) instead of Postgres-only notes: a
  filesystem/Git-backed adapter behind the same repository seam Knowledge
  MCP already uses, or a two-way sync job. This is the single most
  job-relevant integration given the "Obsidian-as-AI-workspace" framing —
  see `docs/APPLICATION_NOTES.md`.
- **Slack / Google Drive / Notion** — `DevBrain_vision.md` §36's stated
  longer-term integration set. Each would be a sixth+ MCP server following
  the exact same `tools → services → repositories/adapters` layering, not a
  new architectural pattern.

## 2. RBAC hardening

Today's `Role` model (viewer/user/admin) is a flat, global three-tier
ordering with a static token→role map (`MCP_API_TOKENS`). Production
hardening would add:

- Per-project or per-team scoping (today, any `Role.USER` token can act on
  any project — there's no tenant/ownership boundary).
- Real user accounts + session-based auth (JWTs with expiry/refresh) instead
  of static bearer tokens issued once in `.env`.
- Token rotation and revocation (`.env`-issued tokens today have no
  expiry or revocation path).
- Audit-log-driven anomaly detection (e.g. flag an actor whose call pattern
  suddenly spikes) — the `audit_logs` table already has everything this
  would read from.

## 3. Idempotency as a first-class schema feature

Currently `create_task`/`create_event`'s idempotency piggybacks on
`audit_logs.arguments` JSONB (`devbrain_common.idempotency`) — correct today
but without a DB-level unique constraint. A dedicated `idempotency_keys`
table (key, tool_name, actor, result_id, expires_at) would let this extend
to every write tool with a real constraint instead of an application-level
scan, and support key expiry.

## 4. Approval matching beyond exact-dict equality

`enforce_approval`'s current match is `arguments == arguments` — exact,
field-for-field. A production system probably wants a looser but still safe
match (e.g. an explicit allowlist of fields that may differ between the
proposal and the executed call, like a server-populated timestamp) rather
than requiring byte-for-byte reconstruction.

## 5. Observability

`DevBrain_vision.md` §17/§32 calls for metrics/tracing as a peer of audit
logging. Today's `structlog`-based structured JSON logging is a solid
foundation; next would be OpenTelemetry tracing across the
tool → service → repository → DB path (each layer boundary above is already
a natural span boundary) and a metrics endpoint (request rate, error rate,
approval-gate latency, rate-limit rejections per actor).

## 6. Production deployment concerns

- Tighten CORS from `allow_origins=["*"]` to the real frontend origin(s)
  (`SECURITY.md`).
- Move secrets out of `.env` into a real secrets manager.
- Postgres: connection pooling tuned for concurrent load (today's
  `session_scope()` opens a fresh session per call — fine for a demo, not
  for production concurrency), read replicas if Knowledge MCP's search load
  grows.
- Swap the in-memory, single-process `RateLimiter` for a shared backend
  (Redis) if DevBrain ever runs multi-process/multi-instance — the
  `RateLimiter` interface is already designed for this swap
  (`packages/common/src/devbrain_common/ratelimit.py`'s own docstring).
- Next.js 14 → 16 upgrade to close the two remaining `npm audit` advisories
  (deferred as a demo-scope tradeoff, `PROGRESS_REPORT.md` Phase 9).
- `mcp` SDK 1.x → 2.x migration (`FastMCP` decorator API → the new
  `MCPServer`/`RequestStateSecurity` redesign) — deliberately deferred
  through this whole build for API stability; worth revisiting once 2.0's
  ecosystem/docs mature (`PROGRESS_REPORT.md` Phase 3's Open Questions).

## 7. Richer activity/audit surface

`GET /activity`'s `result_summary` is currently a coarse status-derived
string ("completed successfully"/"failed"/"denied..."), not a real
per-call summary ("created task 'Fix OAuth tests'") — would need a new
`audit_logs.result` JSON column written by `record_audit_event` itself.
Flagged, not built, in Phase 8's own Open Questions — still open.

## 8. Evaluation beyond the stub-LLM proxy

`tests/eval/`'s scenario suite proves the right *service/orchestrator call*
happens under a deterministic stub LLM — a proxy for "would Claude pick the
right tool," not a replacement for it (documented honestly in that suite's
own module). A true agentic eval would run each scenario against a live
Claude Desktop/Code MCP connection and grade the actual tool-use trace and
final answer — `DEMO.md` covers the manual version of this; automating it
(recording a transcript, scoring against expected tool sequences) is future
work, not attempted here.
