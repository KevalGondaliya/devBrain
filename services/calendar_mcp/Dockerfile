# Calendar MCP — multi-stage, uv-based, non-root.
#
# Build context is the **repo root** (a uv workspace member needs its
# workspace siblings, at minimum `packages/common`, reachable during
# `uv sync`) — see docker-compose.yml's `calendar-mcp` stanza:
#
#   build:
#     context: .
#     dockerfile: services/calendar_mcp/Dockerfile
#
# Do not `docker build services/calendar_mcp` directly — the COPY paths
# below assume the root as context. Mirrors services/task_mcp/Dockerfile.

FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# Only what `uv sync` needs to resolve+install this workspace member and its
# `devbrain-common` workspace dependency — keeps the image build fast and
# avoids pulling in unrelated services (uv tolerates other declared
# workspace members not being present on disk).
COPY pyproject.toml uv.lock ./
COPY packages/common ./packages/common
COPY services/calendar_mcp ./services/calendar_mcp

RUN uv sync --package calendar-mcp --extra dev --no-dev --frozen

FROM python:3.12-slim AS runtime

RUN groupadd --system devbrain && useradd --system --gid devbrain --create-home devbrain

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    CALENDAR_MCP_TRANSPORT=streamable-http \
    CALENDAR_MCP_HOST=0.0.0.0 \
    CALENDAR_MCP_PORT=8005

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages/common /app/packages/common
COPY --from=builder /app/services/calendar_mcp /app/services/calendar_mcp

USER devbrain
EXPOSE 8005

CMD ["python", "-m", "calendar_mcp.server"]
