"""Audit logging: every write tool call must record one of these.

ORCHESTRATION.md §1: "Every write tool call is audited (`audit_logs`: actor,
tool, args, result status, duration, timestamp). Never log secrets or full
auth tokens."
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from devbrain_common.models import AuditLog

# Argument keys (case-insensitive, substring match) whose values are never
# persisted verbatim — the audit log redacts them regardless of nesting.
_SENSITIVE_KEY_MARKERS = (
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
)

_REDACTED = "***redacted***"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive values from a tool-call arguments dict.

    Never mutates the input; returns a new dict/list tree with sensitive
    leaf values replaced by a fixed placeholder.
    """

    def _redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: (_REDACTED if _is_sensitive_key(str(k)) else _redact(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [_redact(v) for v in value]
        return value

    return cast(dict[str, Any], _redact(arguments))


async def record_audit_event(
    session: AsyncSession,
    *,
    actor: str,
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    duration_ms: int | None = None,
) -> AuditLog:
    """Persist one audit log row for a completed (or denied) tool call.

    `status` must be one of `success` / `error` / `denied` (enforced at the
    DB layer by a CHECK constraint). `arguments` is redacted before storage.
    """
    entry = AuditLog(
        actor=actor,
        tool_name=tool_name,
        arguments=redact_arguments(arguments),
        status=status,
        duration_ms=duration_ms,
    )
    session.add(entry)
    await session.flush()
    return entry
