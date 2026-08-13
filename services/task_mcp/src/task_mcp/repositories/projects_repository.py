"""Read-only cross-entity lookup: `create_task` needs to confirm
`project_id` actually refers to an existing project before inserting a
`tasks` row (the FK would raise an opaque `IntegrityError` otherwise). No
project business logic lives here or anywhere in this service — that's
Project MCP's job."""

from __future__ import annotations

import uuid

from devbrain_common.models import Project
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def exists(session: AsyncSession, project_id: uuid.UUID) -> bool:
    stmt = select(Project.id).where(Project.id == project_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
