"""`secondbrain://note/{id}` — read-only note resource."""

from __future__ import annotations

import json
from typing import Any

from devbrain_common.auth import Role
from devbrain_common.errors import DevBrainError, to_error_envelope
from mcp.server.fastmcp import Context, FastMCP

from knowledge_mcp.auth import require_min_role
from knowledge_mcp.services import notes_service
from knowledge_mcp.tools._common import dto_to_dict


def register(mcp: FastMCP) -> None:
    @mcp.resource(
        "secondbrain://note/{id}",
        name="note",
        description="A single note by id, as JSON.",
        mime_type="application/json",
    )
    async def note_resource(id: str, ctx: Context[Any, Any, Any] | None = None) -> str:
        try:
            require_min_role(ctx, Role.VIEWER)
            note = await notes_service.get_note(note_id=id)
            return json.dumps(dto_to_dict(note))
        except DevBrainError as exc:
            return json.dumps(exc.to_error_envelope())
        except Exception as exc:  # noqa: BLE001 - never leak a raw traceback via a resource read
            return json.dumps(to_error_envelope(exc))
