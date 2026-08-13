# DEVELOPMENT.md

How to actually work on this repo. If you're on the exact machine this was
built on (checkout path containing a literal colon,
`.../tools:agents/devBrain/devbrain`), read "Colon-in-path gotchas" below
before anything else — several ordinary commands (`uv run`, `npm run`)
silently fail there and this section documents the workarounds already
baked into the repo/venv.

## First-time setup

```bash
cp .env.example .env                       # edit if you want non-default ports/tokens
uv sync --all-packages --all-extras --dev   # installs EVERY workspace member's deps
                                             # into one shared .venv — see the warning below
docker compose --profile test up -d db_test # ephemeral Postgres+pgvector on :55432
.venv/bin/python -m alembic -c packages/common/alembic.ini upgrade head \
  || (cd packages/common && ../../.venv/bin/python -m alembic upgrade head)
.venv/bin/python scripts/generate_all.py --size default --seed 42 --truncate
```

**Always use `--all-packages --all-extras` with `uv sync`.** A bare `uv sync`
(no flags) only installs the *root* project's own dependencies and silently
**drops** every workspace member's deps (`sqlalchemy`, `pydantic`, `pytest`,
`fastapi`, ...) from the shared `.venv` — this bit an earlier phase and is
worth avoiding from the start (`PROGRESS_REPORT.md` Phase 2).

## Running tests

Start the test DB first (needed for every integration/API/e2e suite, not for
pure-unit suites):

```bash
docker compose --profile test up -d db_test
```

Whole repo (mirrors CI exactly):

```bash
.venv/bin/python -m pytest tests packages services backend scripts -q
```

Per-suite, if you're iterating on one piece:

```bash
.venv/bin/python -m pytest packages/common -q
.venv/bin/python -m pytest scripts/tests/unit -q          # pure, no DB
.venv/bin/python -m pytest scripts/tests/integration -q   # needs db_test
.venv/bin/python -m pytest services/knowledge_mcp/tests -q
.venv/bin/python -m pytest services/project_mcp/tests services/task_mcp/tests -q
.venv/bin/python -m pytest services/github_mcp/tests services/calendar_mcp/tests -q
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m pytest tests/eval -q
.venv/bin/python -m pytest tests/security -q
.venv/bin/python -m pytest tests/e2e -q
```

Lint/format/typecheck:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
MYPYPATH="packages/common/src:scripts:backend/src:services/knowledge_mcp/src:services/project_mcp/src:services/task_mcp/src:services/github_mcp/src:services/calendar_mcp/src" \
  .venv/bin/python -m mypy packages/common/src scripts backend/src \
  services/knowledge_mcp/src services/project_mcp/src services/task_mcp/src \
  services/github_mcp/src services/calendar_mcp/src
```

(The exact `MYPYPATH` string above matches `.github/workflows/ci.yml`'s
`MYPY_SRC_PATHS`/`MYPYPATH` — copy it verbatim rather than retyping.)

## Alembic migration workflow

Migrations live under `packages/common/alembic/versions/` — one shared
schema for every service. From `packages/common/`:

```bash
cd packages/common
../../.venv/bin/python -m alembic upgrade head      # apply all migrations
../../.venv/bin/python -m alembic downgrade -1       # roll back one
../../.venv/bin/python -m alembic revision --autogenerate -m "add some_column"
```

`alembic/env.py` prefers the `DATABASE_URL` env var over `Settings()`'s
default, so pointing a migration run at `db_test` (port 55432) vs. the dev
`db` (port 5432) is just an env var:

```bash
DATABASE_URL=postgresql+asyncpg://devbrain_test:devbrain_test@localhost:55432/devbrain_test \
  ../../.venv/bin/python -m alembic upgrade head
```

Never edit an existing migration file once anything depends on it — add a
new revision instead (`PROGRESS_REPORT.md` Phase 1's own precedent: an early
migration was deleted and regenerated only because *nothing* depended on it
yet).

## Colon-in-path gotchas (this machine specifically)

This repo's own checkout path contains a literal colon
(`/Users/sahil/Documents/tools:agents/devBrain/devbrain`). If you're on a
colon-free path, none of this applies and every tool "just works" via its
normal `uv run`/`npm run` invocation — skip this section.

**Python / `uv run`**: `uv run ...` fails outright
(`error: path segment contains separator ':'`), and even a direct editable
install's `.pth` file gets treated as OS-hidden under this path tree
(CPython's `site.py` silently skips it), so `import devbrain_common` fails
via the normal mechanism. **Workaround, already in place, gitignored**: a
`sitecustomize.py` in `.venv/lib/python3.12/site-packages/` inserts every
workspace package's `src/` onto `sys.path` directly. Practical upshot: call
the venv's binaries directly, never `uv run`:

```bash
.venv/bin/python -m pytest ...
.venv/bin/python -m alembic ...
.venv/bin/python -m ruff ...
.venv/bin/python -m mypy ...
```

`uv sync` itself is unaffected (it doesn't go through this codepath).

**mypy additionally needs `MYPYPATH`** set (see the lint/typecheck section
above) — this one is *not* colon-path-related, it's needed on any machine
once multiple `src`-layout workspace packages coexist; it just wasn't
noticed until this repo had enough of them.

**Node / `npm run` / `npx`**: `npm install` itself is unaffected. But
`npm run build`/`npm run dev`/bare `npx next ...` all fail with
`sh: next: command not found` even though `node_modules/.bin/next` exists —
npm's `run`/`npx` machinery colon-joins `node_modules/.bin` onto `PATH`,
and the literal colon in this repo's path corrupts that join (same root
cause as the Python issue, different tool). **Workaround**: invoke the
binary directly, never through `npm run`/`npx`:

```bash
cd frontend
./node_modules/.bin/next dev
./node_modules/.bin/next build
./node_modules/.bin/next start
```

Docker builds are unaffected either way (the container's own build path has
no colon) but `frontend/Dockerfile` uses the same direct-invocation form for
consistency with what's actually verified on this host.

## Seeding data

```bash
.venv/bin/python scripts/generate_all.py --size {small,default,large} --seed 42 --truncate
```

`small`/`default` sizes are exercised by the test suites; `large` (~90k+
rows, several minutes on CPU for embeddings) was only smoke-tested, not
run end-to-end in CI. `--database-url` targets a non-default database
(e.g. `db_test`); omitted, it uses `DATABASE_URL` from `.env`/`Settings`.

## Running a single MCP server locally

```bash
cd services/knowledge_mcp && ../../.venv/bin/python -m knowledge_mcp.server          # stdio
KNOWLEDGE_MCP_TRANSPORT=streamable-http ../../.venv/bin/python -m knowledge_mcp.server  # HTTP
```

Same pattern for `project_mcp`/`task_mcp`/`github_mcp`/`calendar_mcp` — see
`docs/mcp/overview.md`.

## Running the backend / frontend locally (outside Docker)

```bash
# backend
cd backend && ../.venv/bin/python -m uvicorn devbrain_backend.api.main:app --reload --port 8000

# frontend
cd frontend && ./node_modules/.bin/next dev
```

## Full stack via Docker Compose

```bash
docker compose up -d
```

Brings up Postgres, all five MCP servers, the backend, and the frontend —
see `DEMO.md` for the full walkthrough including approvals and the audit
log.
