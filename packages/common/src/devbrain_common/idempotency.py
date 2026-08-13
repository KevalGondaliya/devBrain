"""Idempotency-key lookups piggybacked on `audit_logs` (DevBrain_vision.md
§16).

Phase 6 generalization: `task_mcp.create_task` and `calendar_mcp.create_event`
(Phases 4/5) each independently implemented this exact pattern — look up the
most recent successful `audit_logs` row for a tool+key, and if the id it
recorded still resolves to a real row, replay that result instead of
inserting a duplicate. Both services' local
`repositories/idempotency_repository.py` copies are now deleted; this is the
one implementation both `tasks_service.create_task` and
`calendar_service.create_event` call.

No dedicated `idempotency_keys` table exists in the shared schema — adding
one (with a DB-level unique constraint on `(tool_name, key)`, which this
JSONB-scan approach cannot offer) would be the cleaner long-term home; see
PROGRESS_REPORT.md Phase 4/6 "Decisions made" for the full tradeoff
writeup. This phase does own `packages/common`'s schema/migrations, but
chose not to add that table now — the JSONB approach already works
correctly (verified via the existing `create_task`/`create_event` tests
this refactor keeps green) and a schema change purely to firm up a
uniqueness guarantee neither caller has hit a real problem from is out of
scope for a "keep behavior identical, consolidate the code" refactor.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devbrain_common.audit import record_audit_event
from devbrain_common.models import AuditLog


async def find_successful_call_by_key(
    session: AsyncSession, *, tool_name: str, idempotency_key: str
) -> AuditLog | None:
    """Most recent successful `audit_logs` row for `tool_name` whose
    `arguments->>'idempotency_key'` matches, or `None` if none exists yet.

    Uses SQLAlchemy's JSONB `->>'key'` operator (`.astext`) — parameterized
    ORM-level comparison, not a raw/string-interpolated SQL query.
    """
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.tool_name == tool_name,
            AuditLog.status == "success",
            AuditLog.arguments["idempotency_key"].astext == idempotency_key,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def check_idempotent_replay[T](
    session: AsyncSession,
    *,
    actor: str,
    tool_name: str,
    idempotency_key: str | None,
    result_key: str,
    get_existing: Callable[[AsyncSession, str], Awaitable[T | None]],
    started: float | None = None,
) -> T | None:
    """The full idempotent-replay check a `create_*` service function opens
    its `unit_of_work()` with.

    If `idempotency_key` is falsy, returns `None` immediately (no lookup —
    the caller didn't ask for idempotency). Otherwise looks up the prior
    successful call; if found and `result_key` (e.g. `"result_task_id"`)
    names a value that still resolves via `get_existing`, records a second
    `audit_logs` row (`idempotent_replay: true`) and returns the existing
    object — the caller should return that instead of inserting a
    duplicate. Returns `None` if there is no prior call, or the prior call's
    referenced row no longer exists (caller proceeds to insert normally).
    """
    if not idempotency_key:
        return None

    prior = await find_successful_call_by_key(
        session, tool_name=tool_name, idempotency_key=idempotency_key
    )
    if prior is None:
        return None

    prior_id = prior.arguments.get(result_key)
    if not isinstance(prior_id, str):
        return None

    existing = await get_existing(session, prior_id)
    if existing is None:
        return None

    await record_audit_event(
        session,
        actor=actor,
        tool_name=tool_name,
        arguments={
            "idempotency_key": idempotency_key,
            "idempotent_replay": True,
            result_key: prior_id,
        },
        status="success",
        duration_ms=int((time.monotonic() - started) * 1000) if started is not None else None,
    )
    return existing
