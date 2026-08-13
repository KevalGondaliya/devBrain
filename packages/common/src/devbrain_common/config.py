"""Centralized application settings, loaded from environment / .env.

Every field here must have a matching entry in the root `.env.example`.
Use `get_settings()` everywhere instead of instantiating `Settings()`
directly — it is cached so the environment is parsed exactly once per
process.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration, sourced from environment variables / .env.

    Field names intentionally mirror the env var names (upper-cased) in
    `.env.example` so the mapping is obvious at a glance.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://devbrain:change-me-locally@localhost:5432/devbrain",
        description="Async SQLAlchemy database URL (postgresql+asyncpg://...).",
    )

    # --- Auth ---
    mcp_api_tokens: str = Field(
        default="",
        description='Comma-separated "token:role" pairs, e.g. "tok:admin,tok2:viewer".',
    )

    # --- Anthropic ---
    anthropic_api_key: str = Field(
        default="", description="Only required in DEVBRAIN_LLM_MODE=real."
    )
    devbrain_llm_mode: Literal["stub", "real"] = Field(
        default="stub",
        description="stub: deterministic, no network call (tests/CI). real: calls Anthropic.",
    )

    # --- Embeddings ---
    embedding_model: str = Field(default="all-MiniLM-L6-v2")

    # --- Logging ---
    log_level: str = Field(default="INFO")
    log_format: Literal["json", "console"] = Field(default="json")

    # --- Rate limiting ---
    rate_limit_per_minute: int = Field(default=120, gt=0)

    # --- Reliability ---
    tool_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Per-tool-call timeout (DevBrain_vision.md §15), via asyncio.wait_for.",
    )

    # --- Dummy data generation ---
    seed_dataset_size: Literal["small", "default", "large"] = Field(default="default")
    seed_random_seed: int = Field(default=42)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide `Settings` singleton (cached after first call).

    Tests that need a fresh read of the environment should call
    `get_settings.cache_clear()` first.
    """
    return Settings()
