"""`devbrain_common.idempotency` — the shared `create_task`/`create_event`
replay-lookup pattern (Phase 4/5 flagged this for Phase 6 to generalize).

`check_idempotent_replay`'s no-DB-access branches (no key given; key given
but no prior call; prior call found but its referenced row is gone) are
unit-tested here against a monkeypatched lookup. The full round trip
against a real `audit_logs` row is covered by `task_mcp`/`calendar_mcp`'s
own integration suites (unchanged behavior after migrating to this shared
module).
"""

from __future__ import annotations

from typing import Any

import pytest
from devbrain_common import idempotency
from devbrain_common.models import AuditLog


class _FakeSession:
    """Stands in for `AsyncSession` — never touched directly here since
    `find_successful_call_by_key` itself is monkeypatched per test."""


async def test_check_idempotent_replay_returns_none_when_no_key_given() -> None:
    async def get_existing(session: Any, prior_id: str) -> Any:
        raise AssertionError("should never be called")

    result = await idempotency.check_idempotent_replay(
        _FakeSession(),  # type: ignore[arg-type]
        actor="alice",
        tool_name="create_task",
        idempotency_key=None,
        result_key="result_task_id",
        get_existing=get_existing,
    )
    assert result is None


async def test_check_idempotent_replay_returns_none_when_no_prior_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_find(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(idempotency, "find_successful_call_by_key", fake_find)

    async def get_existing(session: Any, prior_id: str) -> Any:
        raise AssertionError("should never be called")

    result = await idempotency.check_idempotent_replay(
        _FakeSession(),  # type: ignore[arg-type]
        actor="alice",
        tool_name="create_task",
        idempotency_key="key-1",
        result_key="result_task_id",
        get_existing=get_existing,
    )
    assert result is None


async def test_check_idempotent_replay_returns_existing_and_records_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = AuditLog(
        actor="alice",
        tool_name="create_task",
        arguments={"idempotency_key": "key-1", "result_task_id": "task-123"},
        status="success",
    )

    async def fake_find(*args: Any, **kwargs: Any) -> AuditLog:
        return prior

    recorded: list[dict[str, Any]] = []

    async def fake_record_audit_event(session: Any, **kwargs: Any) -> None:
        recorded.append(kwargs)

    monkeypatch.setattr(idempotency, "find_successful_call_by_key", fake_find)
    monkeypatch.setattr(idempotency, "record_audit_event", fake_record_audit_event)

    async def get_existing(session: Any, prior_id: str) -> str | None:
        assert prior_id == "task-123"
        return "the-existing-task-object"

    result = await idempotency.check_idempotent_replay(
        _FakeSession(),  # type: ignore[arg-type]
        actor="alice",
        tool_name="create_task",
        idempotency_key="key-1",
        result_key="result_task_id",
        get_existing=get_existing,
        started=0.0,
    )
    assert result == "the-existing-task-object"
    assert len(recorded) == 1
    assert recorded[0]["arguments"] == {
        "idempotency_key": "key-1",
        "idempotent_replay": True,
        "result_task_id": "task-123",
    }


async def test_check_idempotent_replay_returns_none_when_referenced_row_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = AuditLog(
        actor="alice",
        tool_name="create_task",
        arguments={"idempotency_key": "key-1", "result_task_id": "task-gone"},
        status="success",
    )

    async def fake_find(*args: Any, **kwargs: Any) -> AuditLog:
        return prior

    monkeypatch.setattr(idempotency, "find_successful_call_by_key", fake_find)

    async def get_existing(session: Any, prior_id: str) -> Any | None:
        return None

    result = await idempotency.check_idempotent_replay(
        _FakeSession(),  # type: ignore[arg-type]
        actor="alice",
        tool_name="create_task",
        idempotency_key="key-1",
        result_key="result_task_id",
        get_existing=get_existing,
    )
    assert result is None
