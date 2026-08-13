# DevBrain backend (Phase 8's FastAPI HTTP surface) — multi-stage, uv-based,
# non-root. Same pattern as every services/*/Dockerfile (see
# services/calendar_mcp/Dockerfile, the freshest template this was copied
# from), with one difference: this workspace member depends on *all five*
# service packages as real importable libraries (Phase 7's agent
# orchestrators call their `services/*.py` layers directly, no MCP
# transport hop — see PROGRESS_REPORT.md Phase 7), so every one of them
# needs to be copied into the build context, not just `packages/common`.
#
# Build context is the **repo root** — see docker-compose.yml's `backend`
# stanza:
#
#   build:
#     context: .
#     dockerfile: backend/Dockerfile
#
# Do not `docker build backend` directly — the COPY paths below assume the
# root as context.

FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# Everything `uv sync` needs to resolve+install this workspace member and
# every workspace dependency it declares (devbrain-common + all five
# service packages) — unlike a single MCP service's own Dockerfile, this
# one can't get away with copying just `packages/common`.
COPY pyproject.toml uv.lock ./
COPY packages/common ./packages/common
COPY services/knowledge_mcp ./services/knowledge_mcp
COPY services/project_mcp ./services/project_mcp
COPY services/task_mcp ./services/task_mcp
COPY services/github_mcp ./services/github_mcp
COPY services/calendar_mcp ./services/calendar_mcp
COPY backend ./backend

RUN uv sync --package devbrain-backend --extra dev --no-dev --frozen

FROM python:3.12-slim AS runtime

RUN groupadd --system devbrain && useradd --system --gid devbrain --create-home devbrain

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages/common /app/packages/common
COPY --from=builder /app/services/knowledge_mcp /app/services/knowledge_mcp
COPY --from=builder /app/services/project_mcp /app/services/project_mcp
COPY --from=builder /app/services/task_mcp /app/services/task_mcp
COPY --from=builder /app/services/github_mcp /app/services/github_mcp
COPY --from=builder /app/services/calendar_mcp /app/services/calendar_mcp
COPY --from=builder /app/backend /app/backend

USER devbrain
EXPOSE 8000

# Calls into the five services' `services/*.py` layers as libraries, not
# over the network — no MCP server needs to be reachable for this to work
# (see docker-compose.yml's `backend` stanza comment for why it only
# depends on `db`, not the five `*-mcp` services).
CMD ["uvicorn", "devbrain_backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
