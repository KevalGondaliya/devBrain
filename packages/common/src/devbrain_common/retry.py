"""Retry-with-backoff helper for transient infrastructure errors.

DevBrain_vision.md §15 ("reliability: timeouts, retries, ..."). Deliberately
small and generic — not a circuit breaker, not per-exception-type tuning
beyond a caller-supplied tuple. Used by `devbrain_common.db.session_scope`
around the commit call (see that module's comment for why that specific
point in the session lifecycle, not everywhere) rather than wrapping every
DB call blindly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

# Exceptions worth retrying by default: transient OS/network-level failures.
# Callers touching the DB layer pass a tuple that also includes
# `sqlalchemy.exc.DBAPIError` (covers driver-level disconnects/operational
# errors) — kept out of the default here so this module has no SQLAlchemy
# dependency of its own.
DEFAULT_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    OSError,
    ConnectionError,
    TimeoutError,
)


async def retry_async[T](
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    retryable: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_EXCEPTIONS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Call `func()` up to `attempts` times, retrying on `retryable` errors.

    Exponential backoff between attempts: `base_delay * 2**attempt_index`,
    capped at `max_delay`. `sleep` is injectable so tests never need a real
    `asyncio.sleep` (pass an async no-op / instrumented fake). Re-raises the
    final attempt's exception unchanged if every attempt fails; any
    exception not in `retryable` propagates immediately without retrying.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    for attempt in range(attempts):
        try:
            return await func()
        except retryable:
            if attempt == attempts - 1:
                raise
            delay = min(max_delay, base_delay * (2**attempt))
            await sleep(delay)

    raise AssertionError("unreachable")  # pragma: no cover
