"""GitHub-MCP-local settings.

Everything shared across services (`database_url`, `mcp_api_tokens`, ...)
lives in `devbrain_common.config.Settings` — import `get_settings()` from
there directly. This module only holds the handful of knobs specific to
*this* server's transport/auth wiring, mirroring
`services/task_mcp/src/task_mcp/config.py`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GithubMCPSettings(BaseSettings):
    """Process-wide settings specific to the GitHub MCP server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Transport ---
    github_mcp_transport: str = Field(
        default="stdio",
        description='"stdio" (local Claude Desktop/Code dev) or "streamable-http"/"sse".',
    )
    github_mcp_host: str = Field(default="127.0.0.1")
    github_mcp_port: int = Field(default=8004)

    # --- Auth ---
    # Role assumed for stdio-transport calls (no bearer token to read
    # locally) — same local-dev carve-out as every sibling MCP server.
    github_mcp_stdio_role: str = Field(default="admin")


@lru_cache(maxsize=1)
def get_github_mcp_settings() -> GithubMCPSettings:
    return GithubMCPSettings()
