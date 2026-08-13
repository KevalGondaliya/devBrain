"""Task-MCP-local settings.

Everything shared across services (`database_url`, `mcp_api_tokens`, ...)
lives in `devbrain_common.config.Settings` — import `get_settings()` from
there directly. This module only holds the handful of knobs specific to
*this* server's transport/auth wiring, mirroring
`services/knowledge_mcp/src/knowledge_mcp/config.py` and
`services/project_mcp/src/project_mcp/config.py`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TaskMCPSettings(BaseSettings):
    """Process-wide settings specific to the Task MCP server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Transport ---
    # `task_mcp_*` (-> env vars `TASK_MCP_*`), not a generic
    # `MCP_HOST`/`MCP_PORT`, since sibling MCP servers in the same compose
    # stack each need their own distinct host/port envs.
    task_mcp_transport: str = Field(
        default="stdio",
        description='"stdio" (local Claude Desktop/Code dev) or "streamable-http"/"sse".',
    )
    task_mcp_host: str = Field(default="127.0.0.1")
    task_mcp_port: int = Field(default=8003)

    # --- Auth ---
    # Role assumed for stdio-transport calls (no bearer token to read
    # locally) — same local-dev carve-out as Knowledge/Project MCP.
    task_mcp_stdio_role: str = Field(default="admin")


@lru_cache(maxsize=1)
def get_task_mcp_settings() -> TaskMCPSettings:
    return TaskMCPSettings()
