# TEST_REPORT.md

QA loop results history. New dated entries are appended; history is never
deleted or overwritten. See `ORCHESTRATION.md` §5 for the protocol this file
follows.

---

## 2026-08-13 — Phase 0-2 QA pass (first pass, by qa-agent)

**Summary: Phase 0-2 QA pass: 71/71 tests passing, lint/type-check clean, 0 regressions found.**

Scope: Phases 0-2 (repo scaffold, shared package + Postgres schema, dummy
data generator). Phase 3 (Knowledge MCP) is being built concurrently by
another agent; `services/knowledge_mcp/` was left untouched per instructions
— its directories are currently empty scaffolding only (untracked, no files
yet), so it contributed no tests and needed no exclusion from lint/type-check
runs.

### 1. Test DB

`docker compose --profile test up -d db_test` → container already running
(`devbrain-db_test-1`, `Up ... (healthy)`), 38+ min uptime from a prior
agent's session. Confirmed healthy via `docker inspect --format='{{.State.Health.Status}}'` → `healthy`.

### 2. Alembic migrations

From `packages/common`, against the test DB URL
(`postgresql+asyncpg://devbrain_test:devbrain_test@localhost:55432/devbrain_test`):

- `.venv/bin/python -m alembic upgrade head` → ran clean, no-op (schema
  already present from Phase 2's own seeding run against `db_test`).
- `alembic current` and `alembic heads` both report `c22d578ddc2b (head)` —
  confirms `db_test` is exactly at the one migration that exists, no drift.

### 3. Full test suite

`.venv/bin/python -m pytest tests packages services backend scripts -q`
(repo root) → **71 passed, 0 failed**, ~11s wall time. Re-ran again after
reseeding `db_test` at `default` size (step 5 below) to confirm no test
depends on a specific pre-existing DB state → still **71 passed**.

Breakdown (via `--collect-only`, no collection errors anywhere):
- `packages/common/tests/unit/*` + `packages/common/tests/integration/test_schema_roundtrip.py` — 50 tests
- `scripts/tests/unit/*` — 20 tests
- `scripts/tests/integration/test_seed_db.py` — 1 test
- `tests/{unit,integration,security,e2e,eval}` — empty (no test files yet, expected — those are cross-service suites for later phases)
- `services/*`, `backend/tests` — empty (no test files yet, expected — Phases 3-9 not built)

No failures, no errors, no skips.

### 4. Lint / type-check

- `.venv/bin/ruff check .` → **All checks passed.**
- `.venv/bin/ruff format --check .` → **48 files already formatted.** (not
  explicitly requested by the QA protocol but run as a low-cost supplement)
- `MYPYPATH="packages/common/src:scripts" .venv/bin/python -m mypy .` →
  **Success: no issues found in 43 source files.** (mypy strict, per root
  `pyproject.toml`)

No exclusions were needed — `services/knowledge_mcp/` has no `.py` files on
disk yet (confirmed via `find services/knowledge_mcp -type f` → empty), so
it produced zero lint/type-check noise despite being mid-edit elsewhere.

**Note on the CI gap Phase 2 flagged:** Phase 2's `PROGRESS_REPORT.md` Open
Questions noted `.github/workflows/ci.yml` was missing `scripts` from its
pytest invocation and `MYPYPATH` from its mypy step. Checked
`.github/workflows/ci.yml` as of this pass (commit `441972c`, already on
`main` ahead of Phase 2's own commit) — **this has already been fixed**: CI
now runs `uv run pytest tests packages services backend scripts -q
--maxfail=1` and sets `MYPYPATH: packages/common/src:scripts` as a job-level
env var. No outstanding CI gap here; not a regression, just superseded by a
prior fix this QA pass hadn't seen until re-checking.

### 5. Dummy data generator — end to end against `db_test`

`.venv/bin/python scripts/generate_all.py --size small --seed 42 --truncate --database-url postgresql+asyncpg://devbrain_test:devbrain_test@localhost:55432/devbrain_test`
→ completed without error (~13s, dominated by embedding model load).

`.venv/bin/python scripts/generate_all.py --size default --seed 42 --truncate --database-url ...` (same DB, on top, `--truncate` again)
→ completed without error (~13s).

Row counts, actual vs. Phase 2's `PROGRESS_REPORT.md` claims:

| Table | small (actual) | small (claimed) | default (actual) | default (claimed) | Match |
|---|---|---|---|---|---|
| projects | 2 | 2 | 20 | 20 | yes |
| meetings | 20 | 20 | 200 | 200 | yes |
| decisions | 50 | 50 | 500 | 500 | yes |
| tasks | 100 | 100 | 1000 | 1000 | yes |
| notes | 100 | 100 | 1000 | 1000 | yes |
| tags | 37 | 37 | 41 | 41 | yes |
| note_tags | 173 | 173 | 1678 | 1678 | yes |
| links | 60 | 60 | 518 | 518 | yes |
| embeddings | 100 | 100 | 1000 | 1000 | yes |
| github_activities | 200 | 200 | 2000 | 2000 | yes |
| calendar_events | 50 | 50 | 500 | 500 | yes |

**No mismatches** — every row count matches Phase 2's documented claims
exactly, for both tiers, on a fresh reseed.

### 6. Data-quality spot-checks (queried directly against seeded `db_test`, `default` size, via `devbrain_common.db.session_scope()`)

| # | Check | Result |
|---|---|---|
| a | Prompt-injection fixture note exists at slug `prompt-injection-fixture-01`, content contains the literal payload | **PASS** — note found, payload string present verbatim in `content` |
| b | At least one pair of conflicting decisions exists | **PASS** — found 2 "Database choice" decisions, statuses `{accepted, superseded}` (the MongoDB/PostgreSQL pair per Phase 2's design) |
| c | At least one overdue task exists | **PASS** — 205 tasks with `due_date < now()` and status in `{todo, in_progress, blocked}` (at `default` size) |
| d | Every FK column in `note_tags`/`links`/`embeddings`/task/meeting/decision resolves to a real parent row (no orphans) | **PASS** — 0 orphans across all 9 checked FK relationships: `note_tags→notes`, `note_tags→tags`, `links→source_notes`, `links→target_notes`, `embeddings→notes`, `tasks→projects`, `meetings→projects`, `decisions→projects`, `decisions→meetings` |

All 4 spot-checks pass.

### 7. `tests/eval`

Not applicable — no scenario set exists yet (Phase 10+ per `ORCHESTRATION.md`
§3/§5). Skipped as instructed, not counted as a failure.

### Regressions found

**None.** Everything that was reported passing in Phase 0/1/2's
`PROGRESS_REPORT.md` entries still passes identically today: 50 tests in
`packages/common`, 20+1 tests in `scripts`, clean ruff/mypy, clean alembic
round-trip, and identical generator row counts at both `small` and `default`
tiers. No `PROGRESS_REPORT.md` regression flags were needed as a result.

---

## 2026-08-13 — Phase 3-6 QA pass (closes out interrupted pass + Phase 6 hardening verification, by qa-agent)

**Summary: 388/388 tests passing (matches Phase 6's claimed total exactly), lint/type-check clean, alembic `downgrade base` → `upgrade head` round-trip clean, all 9 functional spot-checks (5 Knowledge MCP + 3 approval-gate + 1 rate-limit) PASS, 0 regressions in Phases 3-6.**

Scope: Phases 3-6 (Knowledge MCP, Project/Task MCP, GitHub/Calendar MCP,
cross-cutting hardening). Closes out the prior pass's interrupted Knowledge
MCP functional spot-checks (item 5 of the QA brief — never actually run
before this pass) and verifies Phase 6's new approval gate, rate limiter,
and `approvals.consumed_at` migration. Phase 7 (agent workflows) is being
built **concurrently** by another agent in `backend/src/devbrain_backend/agents/`
and `packages/common/src/devbrain_common/llm.py` — neither path was touched
this pass; see the "Concurrent Phase 7 development" note at the bottom for
how its in-flight, uncommitted edits transiently touched two files this
pass does own (`packages/common/pyproject.toml`,
`services/knowledge_mcp/src/knowledge_mcp/{repositories/notes_repository.py,services/notes_service.py}`)
and why that's not counted as a Phase 3-6 regression.

### 1. Test DB + migration round-trip

`docker compose --profile test up -d db_test` → container already running
(`devbrain-db_test-1`), confirmed `healthy` via `docker inspect`.

Migration round-trip against `db_test` (`postgresql+asyncpg://devbrain_test:devbrain_test@localhost:55432/devbrain_test`),
from `packages/common`:
- `alembic downgrade base` → ran clean: `579a1368be9e -> c22d578ddc2b -> ` (drops
  `approvals.consumed_at`, then the whole initial schema).
- `alembic upgrade head` → ran clean: ` -> c22d578ddc2b -> 579a1368be9e` (initial
  schema, then `add approvals.consumed_at` back).
- `alembic current` / `alembic heads` both report `579a1368be9e (head)` after
  the round-trip — no drift. Phase 6's new migration applies cleanly from a
  genuinely empty schema, not just as an incremental `upgrade head` on top of
  an already-migrated DB.

### 2. Full test suite

`.venv/bin/python -m pytest tests packages services backend scripts -q`
(repo root) → **388 passed, 0 failed**, ~18s — **exact match** to Phase 6's
claimed total in `PROGRESS_REPORT.md` ("was 315 before this phase... 388
passed"). This was the first run of the session, before any spot-check
script or concurrent-agent edit had touched `db_test` or the repo tree, so
it's the authoritative baseline number for this pass. Zero regressions.

One pre-existing warning (not a failure, not new this pass):
`IncompleteFieldDefinitionWarning` on `calendar_mcp`'s `test_create_server_registers_tools_without_error`
(`lifespan` field has an unresolved forward reference). Cosmetic, does not
affect test outcome; noting it here since it wasn't called out in the prior
`TEST_REPORT.md` entry (Phase 0-2 pass predates `calendar_mcp` existing).

### 3. Lint / type-check

- `.venv/bin/ruff check .` → **All checks passed.**
- `.venv/bin/ruff format --check .` → **218 files already formatted.**
- `MYPYPATH="packages/common/src:scripts:services/knowledge_mcp/src:services/project_mcp/src:services/task_mcp/src:services/github_mcp/src:services/calendar_mcp/src"
  .venv/bin/python -m mypy packages/common scripts services/knowledge_mcp/src
  services/project_mcp/src services/task_mcp/src services/github_mcp/src
  services/calendar_mcp/src` → **Success: no issues found in 151 source
  files** — exact match to Phase 6's claimed `151 source files` (mypy
  strict, `src/` only per established Phase 3-6 precedent; `backend/` and
  `packages/common/src/devbrain_common/llm.py` deliberately excluded from
  this command's targets, both per that same precedent and per this pass's
  explicit instruction not to touch Phase 7's owned paths).

Both commands were run immediately after step 2, before any concurrent-agent
edit had landed — see the bottom note for what a *later* rerun showed once
Phase 7's in-flight work touched `knowledge_mcp`/`packages/common/pyproject.toml`.

### 4. Reseed `--size default --truncate`, confirm suite still green

`.venv/bin/python scripts/generate_all.py --size default --seed 42
--truncate --database-url postgresql+asyncpg://devbrain_test:devbrain_test@localhost:55432/devbrain_test`
→ completed without error, row counts identical to the Phase 0-2 pass's
documented `default` tier (20 projects / 200 meetings / 500 decisions /
1000 tasks / 1000 notes / 41 tags / 1678 note_tags / 518 links / 1000
embeddings / 2000 github_activities / 500 calendar_events).

`.venv/bin/python -m pytest tests packages services backend scripts -q`
(rerun on top of the fresh reseed) → **388 passed** again. No hidden
coupling to a specific seed run — confirms Phase 3's `knowledge_mcp`
integration suite (and every other integration suite) reseeds/truncates its
own working state via its own session-scoped fixtures regardless of what
was in `db_test` beforehand.

**Test-isolation note worth flagging for future QA passes**: `knowledge_mcp`'s
`tests/integration/conftest.py::seed_small_dataset` fixture is session-scoped
and autouse — it truncates `db_test`, seeds `--size small --seed 42` for its
own suite's duration, then **truncates again at teardown**. Running the full
combined suite therefore always leaves `db_test` back at zero seed rows when
it finishes, regardless of what tier you reseeded beforehand. This is by
design (test isolation) and not a bug, but it means "reseed, then run
anything that needs real data" only holds true if the reseed happens
*after* the last full-suite run, not before it — relevant to step 5 below,
where the functional spot-checks needed a fresh reseed of their own after
this step's suite run emptied the table again.

### 5. Knowledge MCP functional spot-checks (closing out the interrupted pass)

Reseeded `db_test` fresh (`--size default --seed 42 --truncate`) immediately
before running this script, to have real seeded notes/wikilinks/embeddings
available (per the note in step 4 above). Wrote a throwaway script
(`knowledge_spotcheck.py`, deleted after use) importing
`knowledge_mcp.services.{notes_service,search_service,links_service}`
directly against `db_test`:

| # | Check | Result |
|---|---|---|
| a | Create a note (`notes_service.create_note`) | **PASS** — note created (`qa-spotcheck-note-about-reverse-proxies`) |
| b | Keyword search (`mode="keyword"`) finds it by title substring | **PASS** — 1 hit, target found |
| c | Semantic search (`mode="semantic"`) with a paraphrased query ("How do you set up load balancing and terminate TLS for microservices?" vs. the note's actual text about "reverse proxy configuration... load balancing... TLS termination") still finds it | **PASS** — 10 hits, target found, top cosine-similarity score 0.779 — proves the embedding model captures paraphrase-level semantic similarity, not just keyword overlap |
| d | Backlinks + graph traversal on a seeded note with real `[[wikilinks]]` (picked the target of an arbitrary real seeded `Link` row) returns non-empty results | **PASS** — 5 backlinks, 2-hop graph: 16 nodes / 16 edges |
| e | Prompt-injection fixture note (`slug == "prompt-injection-fixture-01"`) fetchable via `notes_service.get_note(slug=...)`, content comes back as an inert `str` | **PASS** — fetched, `content` is `str`, length 381, never `eval`/`exec`d — confirmed by the fact this script itself ran to completion without any side effect from the payload text |

**All 5 PASS.** This closes out the "5. Functional spot-checks on Knowledge
MCP" item that the QA brief flagged as never actually completed in the
earlier interrupted pass.

### 6. Approval-gate functional spot-checks (Phase 6)

Wrote a throwaway script (`approval_spotcheck.py`, deleted after use)
against `task_mcp.services.tasks_service.create_task` +
`devbrain_common.approvals.{request_approval,decide_approval}`:

| # | Check | Result |
|---|---|---|
| a | `Role.USER` actor calls `create_task` with no `approval_id` | **PASS** — raised `ApprovalRequiredError`: *"Tool 'create_task' requires approval before it can execute as role 'user'. Call request_approval with the exact same arguments first."* |
| b | `request_approval` (as the user) → `decide_approval(decision="approved")` (as `Role.ADMIN`, i.e. `decided_by="qa-spotcheck-admin"`) → retry `create_task` with the resulting `approval_id` and the **exact same** call arguments | **PASS** — task created (`id=ff70bdae-...`) once the matching approval was redeemed |
| c | `Role.ADMIN` calls `create_task` directly, no `approval_id` | **PASS** — succeeded immediately (`id=444cc435-...`); the corresponding `audit_logs` row (`tool_name="create_task"`, `actor="qa-spotcheck-admin-direct"`) has `arguments["approval_bypassed_by_admin"] == True` |

**All 3 PASS.** Confirms `enforce_approval`'s documented contract exactly:
`Role.USER` blocked without a valid approval, a properly-requested-and-approved
approval unblocks the identical call, and an admin bypass is always visible
in the audit trail rather than silent.

Cleanup: the 4 `audit_logs` rows + 1 `approvals` row this script committed
(`session_scope()`-based, not a rolled-back test session) were deleted
afterward (`actor` in `{qa-spotcheck-user, qa-spotcheck-admin-direct,
qa-spotcheck, qa-spotcheck-admin}`) — see the note below on why this
mattered for a downstream test.

### 7. Rate-limiting spot-check

Wrote a throwaway script (`ratelimit_spotcheck.py`, deleted after use)
instantiating `devbrain_common.ratelimit.RateLimiter` directly with an
injectable `_clock` callable (the pattern the limiter already supports —
`Settings.rate_limit_per_minute` defaults to 120; this check used a small
`rate_per_minute=5` bucket sized limiter instead of the singleton, no real
sleeping):

| Check | Result |
|---|---|
| 5 calls at a frozen clock (`t=0`) all succeed (burst = one minute's worth), 6th call at the same instant raises `RateLimitedError` | **PASS** |
| Advancing the injected clock by 12s (5 tokens/min ⇒ 1 token/12s) allows exactly one more call, then blocks the next immediate one | **PASS** — confirms refill is driven by the injected clock, not wall-clock time |

**PASS.**

### 8. Docker build / server-wiring verification

Per the QA brief's explicit permission to skip full `docker compose build`
if each service's `test_*_server_wiring.py` exists and passes: confirmed
all five exist (`services/{calendar_mcp,github_mcp,knowledge_mcp,project_mcp,task_mcp}/tests/unit/test_*_server_wiring.py`)
and ran them explicitly: `.venv/bin/python -m pytest services -q -k
server_wiring` → **5 passed** (each calls `create_server()` +
`list_tools()` for real, which is exactly the class of bug Phase 6 found
and fixed once already — a `TYPE_CHECKING`-gated import that broke real
FastMCP registration despite passing every other test). **Full `docker
compose build` skipped this pass** per that guidance, to save time — no
regression risk identified in the wiring layer these tests target.

### `tests/eval`

Not applicable — still no scenario set (Phase 10+). Skipped, not counted as
a failure, same as the prior pass.

### Regressions found

**None in Phases 3-6.** Every number this pass measured matches what
Phases 3-6 claimed in `PROGRESS_REPORT.md` exactly: 388/388 tests (was 315
before Phase 6, confirmed unchanged), 151 mypy-strict source files clean,
ruff clean, alembic round-trip clean including the new `approvals.consumed_at`
migration from a genuinely empty schema, and all 9 functional spot-checks
(5 Knowledge MCP + 3 approval-gate + 1 rate-limit) pass. No
`PROGRESS_REPORT.md` regression flags were needed.

### Concurrent Phase 7 development — transient effects observed, not counted as regressions

Phase 7 was being built concurrently by another agent throughout this pass,
in files this QA pass does not own. Two things were observed as a result,
neither touched or fixed by this pass (out of scope, and the other agent's
in-flight work):

1. **Test count drifted from 388 to 390 partway through the session.** The
   concurrent agent's (uncommitted, still in-flight at the time of this
   entry) edits added `notes_repository.list_since` /
   `notes_service.list_recent_notes` to `knowledge_mcp` — its own diff
   documents this as a deliberate, additive Phase 7 addition (`weekly_digest`
   needs a pure date-range listing no existing search primitive expresses),
   plus 2 new tests in `test_notes_service_crud.py` and an `anthropic`
   dependency added to `packages/common/pyproject.toml`. `git status
   --porcelain` at the end of this pass shows these as uncommitted
   modifications alongside the expected untracked `backend/` and
   `packages/common/src/devbrain_common/llm.py`. This pass's authoritative
   388-passed number (§2 above) was captured *before* these edits landed;
   a rerun later in the session showed 390 passed with the same zero
   failures, consistent with 2 new passing tests being added by the other
   agent, not a Phase 3-6 defect.
2. **A later `mypy`/`ruff` rerun (after the above edits landed) showed two
   new issues**, both inside Phase 7's own in-flight files, not Phase 3-6
   code: `ruff` flagged one `E501` (line too long) in the new
   `notes_repository.list_since` function, and `mypy` flagged
   `packages/common/src/devbrain_common/llm.py:205` (`Cannot find
   implementation or library stub for module named "anthropic"` — the new
   dependency hadn't been `uv sync`'d into this venv yet at the time of the
   rerun). Both are attributable to Phase 7's own uncommitted, in-progress
   work landing mid-session, not to anything this pass touched or to
   Phases 3-6. Not flagged as a `PROGRESS_REPORT.md` regression since
   neither Phase 3-6 nor this pass's own changes caused them; the
   concurrent agent's own session should resolve them as it finishes Phase
   7 (its `pyproject.toml` diff already declares the `anthropic` dependency
   — just needs `uv sync`).

### Housekeeping

`db_test` was left reseeded at `--size default --seed 42` (populated) at
the end of this pass. Stray `audit_logs`/`approvals` rows this pass's own
spot-check scripts committed (§6) were deleted before the final full-suite
rerun, since `generate_all.py --truncate` deliberately never clears
`audit_logs`/`approvals` (by design — real audit-trail data, not seed
data) and one `packages/common` integration test
(`test_schema_roundtrip.py::test_insert_project_task_and_audit_log_roundtrip`)
asserts there's exactly one `tool_name == "create_task"` audit row in the
whole table — worth knowing for any future QA pass that writes real,
committed (non-rolled-back) rows via a spot-check script: clean up
`audit_logs`/`approvals` rows you create, since reseeding alone won't do
it.
