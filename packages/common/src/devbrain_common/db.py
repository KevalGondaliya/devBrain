"""Async SQLAlchemy engine, session factory, and declarative base.

Layering rule (see ORCHESTRATION.md): only repository/adapter code should
import `session_scope` or hold a `AsyncSession` directly. Services receive a
session as a parameter; tools never touch this module at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from devbrain_common.config import get_settings
from devbrain_common.retry import DEFAULT_RETRYABLE_EXCEPTIONS, retry_async

# DevBrain_vision.md §15 ("retries" for transient DB errors): `DBAPIError`
# covers asyncpg-level operational errors/disconnects (SQLAlchemy wraps the
# driver's own exception in this common base regardless of driver), on top
# of the generic OS/network exceptions `retry.DEFAULT_RETRYABLE_EXCEPTIONS`
# already covers.
_RETRYABLE_DB_EXCEPTIONS: tuple[type[Exception], ...] = (
    *DEFAULT_RETRYABLE_EXCEPTIONS,
    DBAPIError,
)


class Base(DeclarativeBase):
    """Shared declarative base for every DevBrain ORM model.

    `type_annotation_map` maps every `Mapped[datetime]` column to a
    timezone-aware `TIMESTAMPTZ` by default, per ORCHESTRATION.md's
    "timestamps as timezone-aware" convention — models never need to spell
    out `DateTime(timezone=True)` themselves.
    """

    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy class-level config dict
        datetime: DateTime(timezone=True),
    }


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use.

    Pass `database_url` explicitly (e.g. in tests pointed at `db_test`) to
    force a fresh engine bound to that URL.
    """
    global _engine, _session_factory
    url = database_url or get_settings().database_url
    if _engine is None or str(_engine.url) != url:
        _engine = create_async_engine(url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory, creating it on first use."""
    get_engine(database_url)
    assert _session_factory is not None  # noqa: S101 - invariant enforced by get_engine
    return _session_factory


@asynccontextmanager
async def session_scope(
    database_url: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Yield an `AsyncSession`, committing on success and rolling back on error.

    Usage:
        async with session_scope() as session:
            session.add(obj)
    """
    factory = get_session_factory(database_url)
    async with factory() as session:
        try:
            yield session
            # Retry only the commit itself (DevBrain_vision.md §15): the
            # point in this session's lifecycle closest to real network I/O
            # and where a transient connection drop is most likely to
            # surface. Safe to retry blindly — `commit()` either fully
            # applies or the transaction never lands; there is no partial-
            # write state a retry could duplicate.
            await retry_async(session.commit, retryable=_RETRYABLE_DB_EXCEPTIONS)
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the process-wide engine (call on shutdown / between test runs)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
