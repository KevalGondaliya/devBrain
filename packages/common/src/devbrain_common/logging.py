"""structlog configuration shared by every DevBrain service.

Call `configure_logging()` once at process start (MCP server entrypoint,
backend app factory, scripts). Respects `LOG_LEVEL` / `LOG_FORMAT` from
`devbrain_common.config.Settings`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from devbrain_common.config import get_settings

_configured = False


def configure_logging(*, force: bool = False) -> None:
    """Configure structlog + stdlib logging for this process.

    Idempotent: subsequent calls are no-ops unless `force=True`. Safe to
    call from every entrypoint without worrying about double-configuration.
    """
    global _configured
    if _configured and not force:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")
    _configured = True


def get_logger(*args: object, **kwargs: object) -> Any:
    """Thin wrapper around `structlog.get_logger` — configures logging lazily."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(*args, **kwargs)
