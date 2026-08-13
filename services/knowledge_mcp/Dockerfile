# Knowledge MCP — multi-stage, uv-based, non-root.
#
# Build context is the **repo root** (a uv workspace member needs its
# workspace siblings, at minimum `packages/common`, reachable during
# `uv sync`) — see docker-compose.yml's `knowledge-mcp` stanza:
#
#   build:
#     context: .
#     dockerfile: services/knowledge_mcp/Dockerfile
#
# Do not `docker build services/knowledge_mcp` directly — the COPY paths
# below assume the root as context.

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
# workspace members not being present on disk; see PROGRESS_REPORT.md
# Phase 3 "Decisions made").
COPY pyproject.toml uv.lock ./
COPY packages/common ./packages/common
COPY services/knowledge_mcp ./services/knowledge_mcp

RUN uv sync --package knowledge-mcp --extra dev --no-dev --frozen

FROM python:3.12-slim AS runtime

RUN groupadd --system devbrain && useradd --system --gid devbrain --create-home devbrain

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    KNOWLEDGE_MCP_TRANSPORT=streamable-http \
    KNOWLEDGE_MCP_HOST=0.0.0.0 \
    KNOWLEDGE_MCP_PORT=8001

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages/common /app/packages/common
COPY --from=builder /app/services/knowledge_mcp /app/services/knowledge_mcp

USER devbrain
EXPOSE 8001

CMD ["python", "-m", "knowledge_mcp.server"]
