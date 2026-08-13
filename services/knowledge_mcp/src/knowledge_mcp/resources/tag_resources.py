"""`secondbrain://tag/{name}` — read-only tag resource (name + note count)."""

from __future__ import annotations

import json
from typing import Any

from devbrain_common.auth import Role
from devbrain_common.errors import DevBrainError, NotFoundError, to_error_envelope
from mcp.server.fastmcp import Context, FastMCP

from knowledge_mcp.auth import require_min_role
from knowledge_mcp.services import tags_service
from knowledge_mcp.tools._common import dto_to_dict


def register(mcp: FastMCP) -> None:
    @mcp.resource(
        "secondbrain://tag/{name}",
        name="tag",
        description="A single tag by name, with its note count, as JSON.",
        mime_type="application/json",
    )
    async def tag_resource(name: str, ctx: Context[Any, Any, Any] | None = None) -> str:
        try:
            require_min_role(ctx, Role.VIEWER)
            tags = await tags_service.list_tags()
            normalized = tags_service.normalize_tag_name(name)
            match = next((t for t in tags if t.name == normalized), None)
            if match is None:
                raise NotFoundError(f"Tag {name!r} not found.")
            return json.dumps(dto_to_dict(match))
        except DevBrainError as exc:
            return json.dumps(exc.to_error_envelope())
        except Exception as exc:  # noqa: BLE001 - never leak a raw traceback via a resource read
            return json.dumps(to_error_envelope(exc))
