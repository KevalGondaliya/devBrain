"""`devbrain_common.retry` — retry-with-backoff for transient errors.

Injects a fake async `sleep` so nothing here actually waits in real time.
"""

from __future__ import annotations

import asyncio

import pytest
from devbrain_common.retry import retry_async


class _Sleeps:
    """Records requested delays instead of actually sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


async def test_retry_async_returns_immediately_on_first_success() -> None:
    calls = 0

    async def func() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    sleeps = _Sleeps()
    result = await retry_async(func, sleep=sleeps)
    assert result == "ok"
    assert calls == 1
    assert sleeps.calls == []


async def test_retry_async_retries_then_succeeds() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("transient")
        return "recovered"

    sleeps = _Sleeps()
    result = await retry_async(flaky, attempts=5, base_delay=0.1, sleep=sleeps)
    assert result == "recovered"
    assert attempts == 3
    # Exponential backoff: 0.1, 0.2 for the two failed attempts.
    assert sleeps.calls == [0.1, 0.2]


async def test_retry_async_reraises_after_exhausting_attempts() -> None:
    async def always_fails() -> None:
        raise ConnectionError("still down")

    sleeps = _Sleeps()
    with pytest.raises(ConnectionError, match="still down"):
        await retry_async(always_fails, attempts=3, base_delay=0.01, sleep=sleeps)
    assert len(sleeps.calls) == 2  # slept between attempts 1->2 and 2->3, not after the last


async def test_retry_async_does_not_retry_non_retryable_exceptions() -> None:
    calls = 0

    async def raises_value_error() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("not transient")

    sleeps = _Sleeps()
    with pytest.raises(ValueError, match="not transient"):
        await retry_async(
            raises_value_error, attempts=5, retryable=(ConnectionError,), sleep=sleeps
        )
    assert calls == 1
    assert sleeps.calls == []


async def test_retry_async_delay_capped_at_max_delay() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise ConnectionError("transient")
        return "ok"

    sleeps = _Sleeps()
    await retry_async(flaky, attempts=5, base_delay=1.0, max_delay=1.5, sleep=sleeps)
    assert sleeps.calls == [1.0, 1.5, 1.5]  # 1.0, 2.0->capped 1.5, 4.0->capped 1.5


def test_retry_async_rejects_non_positive_attempts() -> None:
    async def func() -> None:
        return None

    with pytest.raises(ValueError, match="attempts must be >= 1"):
        asyncio.run(retry_async(func, attempts=0))
