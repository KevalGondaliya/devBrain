"""Shared tool-wrapper helpers: error translation, timeout, DTO
serialization — the pieces every service's `tools/_common.py` reinvented
identically in Phases 3-5.

`handle_tool_errors` is the outer decorator every `@mcp.tool()` function in
every service wraps itself in (applied *before* `@mcp.tool(...)`, i.e.
closest to the function). It now does two things:

1. Enforces `Settings.tool_timeout_seconds` via `asyncio.wait_for`
   (DevBrain_vision.md §15/§24 — "504 Timeout"), raising
   `UpstreamTimeoutError` if the wrapped call doesn't finish in time.
2. Translates any exception into a FastMCP `ToolError` carrying the
   structured `{"error": {"code", "message"}}` envelope — never a raw
   traceback/exception string back to the client. FastMCP's own default
   tool-error wrapping (`mcp.server.fastmcp.tools.base.Tool.run`) does
   `f"Error executing tool {name}: {e}"`, which for a non-`DevBrainError`
   exception would forward `str(e)` (potentially raw internals, e.g. a
   driver error message) straight to the client — this decorator
   intercepts first so that never happens.

Rate limiting is deliberately *not* here — see
`devbrain_common.mcp_auth.make_require_min_role`'s docstring for where it
lives and why (it needs the resolved actor, which isn't available until
that call runs inside the wrapped function body).
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

from devbrain_common.config import get_settings
from devbrain_common.errors import DevBrainError, UpstreamTimeoutError, to_error_envelope


def handle_tool_errors[F: Callable[..., Awaitable[Any]]](func: F) -> F:
    """Enforce the per-call timeout, then translate any exception into a
    `ToolError` carrying the structured `{"error": {"code", "message"}}`
    envelope. See module docstring for the full rationale."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        timeout_seconds = get_settings().tool_timeout_seconds
        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
        except TimeoutError as exc:
            raise ToolError(json.dumps(UpstreamTimeoutError().to_error_envelope())) from exc
        except DevBrainError as exc:
            raise ToolError(json.dumps(exc.to_error_envelope())) from exc
        except Exception as exc:  # noqa: BLE001 - deliberate error-boundary catch-all
            raise ToolError(json.dumps(to_error_envelope(exc))) from exc

    return wrapper  # type: ignore[return-value]


def dto_to_dict(dto: Any) -> dict[str, Any]:
    """Convert a `dataclasses.dataclass` DTO to a JSON-ready dict
    (datetimes -> ISO 8601 strings)."""

    def _convert(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {k: _convert(v) for k, v in dataclasses.asdict(value).items()}
        if isinstance(value, list):
            return [_convert(v) for v in value]
        if isinstance(value, dict):
            return {k: _convert(v) for k, v in value.items()}
        return value

    return dict(_convert(dto))
