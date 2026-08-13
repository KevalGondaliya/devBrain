# SECURITY.md

Reviewer-skim version of DevBrain's security posture. Full detail, module by
module and test by test: `docs/mcp/security.md`. This file is the summary.

## Posture in one paragraph

Every MCP server (and the FastAPI backend that wraps them) enforces the same
five controls, from one shared `packages/common` implementation, not five
divergent copies: **authentication** (bearer token → role), **authorization**
(role-tiered, per-tool minimum), **a human-in-the-loop approval gate** for
every medium-and-above risk write, **audit logging** of every write attempt
(success, failure, or denial), and **rate limiting** per actor. Claude (or
any LLM) is never the final authority for any of these — it can propose, it
cannot approve itself, and its output is never converted into a tool call or
an approval decision anywhere in this codebase.

## Controls

| Control | Implementation | Tests |
|---|---|---|
| Auth | `devbrain_common.auth.TokenStore`, `Role` (viewer < user < admin), `MCP_API_TOKENS` env var | `packages/common/tests/unit/test_auth.py`, `backend/tests/api/test_auth_endpoints.py` |
| Authorization | `require_min_role` on every tool/route, first line of every body | `tests/security/test_authorization_boundaries.py` |
| Input validation | Pydantic/type-hint validated tool params, no raw dicts reach a service | `tests/security/test_malicious_arguments.py` |
| No raw SQL | SQLAlchemy ORM only, confined to `repositories/`; no `execute_sql`-shaped tool anywhere | code review / `docs/mcp/tool-design.md` |
| Approval gate | `devbrain_common.approvals` — request → admin decide → single-use consume; high-risk requires admin **and** approval together | every service's `test_approval_gate*.py`, `backend/tests/api/test_approvals_endpoints.py`, `tests/e2e/test_full_stack_e2e.py` |
| Audit logging | `devbrain_common.audit.record_audit_event`, redacts secrets/tokens by key-name pattern | `packages/common/tests/unit/test_audit_redaction.py`, `backend/tests/api/test_read_endpoints.py` |
| Rate limiting | `devbrain_common.ratelimit.RateLimiter`, per-actor token bucket | `packages/common/tests/unit/test_ratelimit.py` |
| Prompt-injection defense | Untrusted content quarantined in prompts (`build_prompt`'s `untrusted_sections`), and — the control that actually matters — no LLM output is ever load-bearing for a tool call or approval decision | `tests/security/test_prompt_injection.py`, `backend/tests/integration/test_safe_write_integration.py` |
| Structured errors | `DevBrainError` hierarchy → `{"error": {"code","message"}}`, never a raw traceback | `packages/common/tests/unit/test_errors.py` |
| Timeouts | `asyncio.wait_for` per tool call, `TOOL_TIMEOUT_SECONDS` | `packages/common/tests/unit/test_mcp_tooling.py` |
| Idempotency | `devbrain_common.idempotency` — safe retries for `create_task`/`create_event` | each service's `test_*_service.py` idempotency cases |
| Dependency scanning | `uv run pip-audit` in CI (advisory); `npm audit` checked manually for the frontend | `.github/workflows/ci.yml` |
| Secrets management | `.env` only, gitignored; `.env.example` kept in sync; no secret ever in a commit | repo history |

## Known, documented limits (honest, not hidden)

- **CORS** on the FastAPI backend is `allow_origins=["*"]` — local-dev/demo
  only, documented in `backend/src/devbrain_backend/api/main.py`'s module
  docstring. Needs tightening to a real frontend origin before any actual
  deployment.
- **No OAuth, no SSRF protection, no token rotation** yet — not applicable
  today since GitHub/Calendar are fake adapters making zero outbound network
  calls. Required once `ROADMAP.md`'s real-API-integration work lands.
- **Approval `arguments` matching is exact-dict equality** — a caller must
  reconstruct the precise argument dict a write tool builds internally
  (documented per-tool in each tool's MCP description). Workable for this
  project's demo flow; a fuzzier "semantic" match wasn't attempted.
- **Idempotency piggybacks on `audit_logs.arguments` JSONB**, not a
  dedicated table with a DB-level unique constraint — works correctly today,
  documented tradeoff (`ROADMAP.md`).
- **npm audit reports 2 outstanding high-severity advisories** against
  Next.js 14.2.x/postcss whose fix needs a Next 16 major bump — deferred,
  tracked in `ROADMAP.md`.

## Reporting

This is a portfolio/demo project over synthetic data with no production
deployment — there is no live attack surface to report against. If you're
reviewing this as a hiring exercise and see something that should be fixed,
open an issue or say so directly; this file will be updated.
