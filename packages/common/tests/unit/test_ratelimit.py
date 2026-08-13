from __future__ import annotations

import pytest
from devbrain_common.errors import RateLimitedError
from devbrain_common.ratelimit import RateLimiter


class FakeClock:
    """Deterministic stand-in for `time.monotonic` — advance it explicitly."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def make_limiter(rate_per_minute: int, clock: FakeClock) -> RateLimiter:
    return RateLimiter(rate_per_minute=rate_per_minute, _clock=clock)


def test_rate_per_minute_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimiter(rate_per_minute=0)
    with pytest.raises(ValueError, match="positive"):
        RateLimiter(rate_per_minute=-5)


def test_allows_up_to_burst_capacity_then_blocks() -> None:
    clock = FakeClock()
    limiter = make_limiter(3, clock)

    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False  # bucket exhausted, no time passed


def test_tokens_refill_over_time() -> None:
    clock = FakeClock()
    limiter = make_limiter(60, clock)  # 1 token/sec

    for _ in range(60):
        assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False

    clock.advance(1.0)  # one token's worth of time
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False


def test_refill_never_exceeds_burst_capacity() -> None:
    clock = FakeClock()
    limiter = make_limiter(5, clock)

    clock.advance(1000.0)  # huge idle gap before first use
    used = sum(1 for _ in range(10) if limiter.allow("alice"))
    assert used == 5  # capped at the bucket size, not unlimited


def test_actors_have_independent_buckets() -> None:
    clock = FakeClock()
    limiter = make_limiter(1, clock)

    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False
    assert limiter.allow("bob") is True  # bob's bucket is untouched


def test_check_raises_rate_limited_error_when_exhausted() -> None:
    clock = FakeClock()
    limiter = make_limiter(1, clock)

    limiter.check("alice")  # consumes the only token, should not raise
    with pytest.raises(RateLimitedError):
        limiter.check("alice")


def test_reset_single_actor() -> None:
    clock = FakeClock()
    limiter = make_limiter(1, clock)

    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False
    limiter.reset("alice")
    assert limiter.allow("alice") is True


def test_reset_all_actors() -> None:
    clock = FakeClock()
    limiter = make_limiter(1, clock)

    limiter.allow("alice")
    limiter.allow("bob")
    assert limiter.allow("alice") is False
    assert limiter.allow("bob") is False

    limiter.reset()
    assert limiter.allow("alice") is True
    assert limiter.allow("bob") is True
