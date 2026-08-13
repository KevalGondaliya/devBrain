"""`devbrain_common.mcp_tooling` — the consolidated `handle_tool_errors`
(error envelope + per-call timeout) / `dto_to_dict`.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from devbrain_common import mcp_tooling
from devbrain_common.config import get_settings
from devbrain_common.errors import NotFoundError
from mcp.server.fastmcp.exceptions import ToolError


@dataclass(frozen=True)
class InnerDTO:
    name: str


@dataclass(frozen=True)
class OuterDTO:
    id: str
    when: datetime
    items: list[str]
    inner: InnerDTO


def test_dto_to_dict_converts_datetime_and_nested_dataclass() -> None:
    dto = OuterDTO(
        id="abc",
        when=datetime(2026, 1, 1, tzinfo=UTC),
        items=["a", "b"],
        inner=InnerDTO(name="x"),
    )
    result = mcp_tooling.dto_to_dict(dto)
    assert result["id"] == "abc"
    assert result["when"] == "2026-01-01T00:00:00+00:00"
    assert result["items"] == ["a", "b"]
    assert result["inner"] == {"name": "x"}


async def test_handle_tool_errors_translates_devbrain_error_to_structured_envelope() -> None:
    @mcp_tooling.handle_tool_errors
    async def boom() -> None:
        raise NotFoundError("Task not found.")

    with pytest.raises(ToolError) as exc_info:
        await boom()

    envelope = json.loads(str(exc_info.value))
    assert envelope == {"error": {"code": "not_found", "message": "Task not found."}}


async def test_handle_tool_errors_never_leaks_raw_exception_text() -> None:
    @mcp_tooling.handle_tool_errors
    async def boom() -> None:
        raise RuntimeError("super secret internal detail: password=hunter2")

    with pytest.raises(ToolError) as exc_info:
        await boom()

    envelope = json.loads(str(exc_info.value))
    assert envelope["error"]["code"] == "internal_error"
    assert "hunter2" not in envelope["error"]["message"]
    assert "password" not in envelope["error"]["message"]


async def test_handle_tool_errors_passes_through_success() -> None:
    @mcp_tooling.handle_tool_errors
    async def ok(x: int) -> int:
        return x * 2

    assert await ok(21) == 42


async def test_handle_tool_errors_maps_timeout_to_upstream_timeout_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "0.05")
    get_settings.cache_clear()
    try:

        @mcp_tooling.handle_tool_errors
        async def slow() -> None:
            await asyncio.sleep(1.0)

        with pytest.raises(ToolError) as exc_info:
            await slow()

        envelope = json.loads(str(exc_info.value))
        assert envelope == {
            "error": {"code": "upstream_timeout", "message": "The operation timed out."}
        }
    finally:
        monkeypatch.delenv("TOOL_TIMEOUT_SECONDS", raising=False)
        get_settings.cache_clear()


async def test_handle_tool_errors_does_not_time_out_fast_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "5")
    get_settings.cache_clear()
    try:

        @mcp_tooling.handle_tool_errors
        async def fast() -> str:
            await asyncio.sleep(0.01)
            return "done"

        assert await fast() == "done"
    finally:
        monkeypatch.delenv("TOOL_TIMEOUT_SECONDS", raising=False)
        get_settings.cache_clear()
