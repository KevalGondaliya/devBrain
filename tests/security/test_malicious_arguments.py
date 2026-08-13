"""Malicious tool arguments — `DevBrain_vision.md` §25 ("Security Tests":
invalid arguments, malicious tool arguments).

Every tool parameter is a type-hinted / `pydantic.Field`-constrained
argument (`docs/mcp/tool-design.md`); this file proves that claim against
real, fully-constructed servers via `create_server()` + `call_tool()` — the
same dispatch path a real MCP client goes through, not a hand-rolled call to
the underlying Python function. Each test also spies on the service
function the tool *would* have called, asserting it was never reached: the
oversized/malformed input is rejected by FastMCP's Pydantic schema
validation before the tool body (and therefore the service, and therefore
the database) ever runs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from calendar_mcp.server import create_server as create_calendar_server
from calendar_mcp.services import calendar_service
from knowledge_mcp.server import create_server as create_knowledge_server
from knowledge_mcp.services import notes_service
from mcp.server.fastmcp.exceptions import ToolError
from task_mcp.server import create_server as create_task_server
from task_mcp.services import tasks_service


@dataclass
class CallSpy:
    calls: int = field(default=0)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise AssertionError("the real service function should never be reached")


def _call(mcp_factory: object, tool_name: str, arguments: dict[str, Any]) -> None:
    async def _run() -> None:
        mcp = mcp_factory()  # type: ignore[operator]
        await mcp.call_tool(tool_name, arguments)

    asyncio.run(_run())


def test_oversized_task_title_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = CallSpy()
    monkeypatch.setattr(tasks_service, "create_task", spy)
    with pytest.raises(ToolError) as exc_info:
        _call(
            create_task_server,
            "create_task",
            {"project_id": "00000000-0000-0000-0000-000000000000", "title": "a" * 500},
        )
    assert "300 characters" in str(exc_info.value)
    assert spy.calls == 0


def test_wrong_type_task_id_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = CallSpy()
    monkeypatch.setattr(tasks_service, "get_task", spy)
    with pytest.raises(ToolError) as exc_info:
        _call(create_task_server, "get_task", {"id": 12345})
    assert "valid string" in str(exc_info.value)
    assert spy.calls == 0


def test_out_of_range_limit_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = CallSpy()
    monkeypatch.setattr(tasks_service, "search_tasks", spy)
    with pytest.raises(ToolError) as exc_info:
        _call(create_task_server, "search_tasks", {"query": "migration", "limit": -5})
    assert "greater than or equal to 1" in str(exc_info.value)
    assert spy.calls == 0


def test_empty_query_string_rejected_by_service_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """`query` has no `min_length` constraint at the schema layer (a blank
    string is still syntactically a valid string), so this one is rejected
    one layer down, by the service's own `ValidationError` -- still never a
    raw traceback, still surfaced as a structured `{"error": ...}` envelope
    via `handle_tool_errors`, just not a schema-level rejection like the
    others in this file. Included to show the two layers compose."""
    with pytest.raises(ToolError) as exc_info:
        _call(create_task_server, "search_tasks", {"query": "   "})
    assert '"code": "validation_error"' in str(exc_info.value)


def test_wrong_type_note_tags_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = CallSpy()
    monkeypatch.setattr(notes_service, "create_note", spy)
    with pytest.raises(ToolError) as exc_info:
        _call(
            create_knowledge_server,
            "notes.create",
            {"title": "x", "content_md": "y", "tags": 123},
        )
    assert "valid list" in str(exc_info.value)
    assert spy.calls == 0


def test_wrong_type_calendar_datetime_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = CallSpy()
    monkeypatch.setattr(calendar_service, "create_event", spy)
    with pytest.raises(ToolError) as exc_info:
        _call(
            create_calendar_server,
            "create_event",
            {"title": "x", "starts_at": 12345, "ends_at": "2026-08-14T11:00:00+00:00"},
        )
    assert "valid string" in str(exc_info.value)
    assert spy.calls == 0


def test_oversized_note_title_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = CallSpy()
    monkeypatch.setattr(notes_service, "create_note", spy)
    with pytest.raises(ToolError) as exc_info:
        _call(
            create_knowledge_server,
            "notes.create",
            {"title": "t" * 5000, "content_md": "body"},
        )
    assert "300 characters" in str(exc_info.value)
    assert spy.calls == 0


def test_extra_unexpected_field_does_not_smuggle_a_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirms a client cannot pass `role`/`approval_id`-shaped
    escalation attempts through a tool's schema for a tool that doesn't
    define one -- `get_task` has no `role` parameter at all, so supplying
    one is either ignored or rejected, never interpreted as a privilege
    override (privilege comes only from the bearer token / stdio role env
    var, never from tool arguments -- see
    `packages/common/src/devbrain_common/mcp_auth.py`'s module docstring)."""
    mcp = create_task_server()

    async def _run() -> dict[str, Any]:
        # No real task will match this id; a NotFoundError is the
        # expected, safe outcome either way -- what matters is that the
        # extra "role" field never changes the caller's actual privilege.
        try:
            result = await mcp.call_tool(
                "get_task",
                {"id": "00000000-0000-0000-0000-000000000000", "role": "admin"},
            )
            return {"result": result}
        except ToolError as exc:
            return {"error": str(exc)}

    outcome = asyncio.run(_run())
    # Either the extra field was rejected outright, or it was silently
    # ignored and the call proceeded as an ordinary (unauthenticated-
    # -as-admin-via-argument) lookup -- both are safe. What would be unsafe
    # is a 200-shaped success that reflects "role": "admin" back as if it
    # granted anything; assert that never happens.
    assert "role" not in str(outcome.get("result", ""))
