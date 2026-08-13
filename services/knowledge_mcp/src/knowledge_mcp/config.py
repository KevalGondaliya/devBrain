"""Knowledge-MCP-local settings.

Everything shared across services (`database_url`, `mcp_api_tokens`,
`embedding_model`, ...) lives in `devbrain_common.config.Settings` — import
`get_settings()` from there directly. This module only holds the handful of
knobs that are specific to *this* server's transport/auth wiring and have no
reason to live in the shared package.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KnowledgeMCPSettings(BaseSettings):
    """Process-wide settings specific to the Knowledge MCP server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Transport ---
    # Field names are prefixed `knowledge_mcp_*` (-> env vars
    # `KNOWLEDGE_MCP_*`) rather than a generic `MCP_HOST`/`MCP_PORT` on
    # purpose — Phase 4/5 add sibling MCP servers in the same compose stack
    # that need their own distinct host/port envs.
    knowledge_mcp_transport: str = Field(
        default="stdio",
        description='"stdio" (local Claude Desktop/Code dev) or "streamable-http"/"sse".',
    )
    knowledge_mcp_host: str = Field(default="127.0.0.1")
    knowledge_mcp_port: int = Field(default=8001)

    # --- Auth ---
    # second-brain-mcp-plan.md §5: "Bearer-token auth middleware on the
    # HTTP/SSE transport (skip only for local stdio dev mode)". stdio has no
    # per-request Authorization header to read, so a fixed local-dev role is
    # used instead; override to a lower role to exercise permission-denied
    # paths locally without standing up the HTTP transport.
    knowledge_mcp_stdio_role: str = Field(default="admin")


@lru_cache(maxsize=1)
def get_knowledge_mcp_settings() -> KnowledgeMCPSettings:
    return KnowledgeMCPSettings()
