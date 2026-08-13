"""`tools._common` — error translation + DTO serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from calendar_mcp.tools._common import dto_to_dict, handle_tool_errors
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
    result = dto_to_dict(dto)
    assert result["id"] == "abc"
    assert result["when"] == "2026-01-01T00:00:00+00:00"
    assert result["items"] == ["a", "b"]
    assert result["inner"] == {"name": "x"}


async def test_handle_tool_errors_translates_devbrain_error_to_structured_envelope() -> None:
    @handle_tool_errors
    async def boom() -> None:
        raise NotFoundError("Event not found.")

    with pytest.raises(ToolError) as exc_info:
        await boom()

    envelope = json.loads(str(exc_info.value))
    assert envelope == {"error": {"code": "not_found", "message": "Event not found."}}


async def test_handle_tool_errors_never_leaks_raw_exception_text() -> None:
    @handle_tool_errors
    async def boom() -> None:
        raise RuntimeError("super secret internal detail: password=hunter2")

    with pytest.raises(ToolError) as exc_info:
        await boom()

    envelope = json.loads(str(exc_info.value))
    assert envelope["error"]["code"] == "internal_error"
    assert "hunter2" not in envelope["error"]["message"]
    assert "password" not in envelope["error"]["message"]


async def test_handle_tool_errors_passes_through_success() -> None:
    @handle_tool_errors
    async def ok(x: int) -> int:
        return x * 2

    assert await ok(21) == 42
