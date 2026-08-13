"""In-memory token-bucket rate limiter, keyed by actor.

Deliberately simple and process-local (no Redis) — fine for a single-process
demo deployment. If DevBrain ever runs multi-process, swap the `_Bucket`
store for a shared backend behind the same `RateLimiter` interface.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from devbrain_common.config import get_settings
from devbrain_common.errors import RateLimitedError


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


@dataclass
class RateLimiter:
    """Token-bucket limiter: `rate_per_minute` tokens refill continuously per actor.

    Each bucket holds at most `rate_per_minute` tokens (burst = one minute's
    worth). `allow(actor)` consumes one token and returns True, or returns
    False (bucket empty) without consuming anything.
    """

    rate_per_minute: int
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _clock: Callable[[], float] = field(default=time.monotonic)

    def __post_init__(self) -> None:
        if self.rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")

    def _refill(self, bucket: _Bucket, now: float) -> None:
        elapsed = max(0.0, now - bucket.last_refill)
        refill_amount = elapsed * (self.rate_per_minute / 60.0)
        bucket.tokens = min(float(self.rate_per_minute), bucket.tokens + refill_amount)
        bucket.last_refill = now

    def allow(self, actor: str) -> bool:
        """Attempt to consume one token for `actor`. Returns whether it was allowed."""
        now = self._clock()
        bucket = self._buckets.get(actor)
        if bucket is None:
            bucket = _Bucket(tokens=float(self.rate_per_minute), last_refill=now)
            self._buckets[actor] = bucket
        else:
            self._refill(bucket, now)

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False

    def check(self, actor: str) -> None:
        """Like `allow`, but raises `RateLimitedError` instead of returning False."""
        if not self.allow(actor):
            raise RateLimitedError(f"Rate limit exceeded for actor '{actor}'.")

    def reset(self, actor: str | None = None) -> None:
        """Reset a single actor's bucket, or every bucket if `actor` is None."""
        if actor is None:
            self._buckets.clear()
        else:
            self._buckets.pop(actor, None)


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    """Return the process-wide `RateLimiter` singleton, sized from
    `Settings.rate_limit_per_minute`.

    Phase 6: this is what `devbrain_common.mcp_auth.make_require_min_role`
    checks (keyed by actor) on every tool call across all five MCP
    servers — the single enforced limiter, not five independent copies.
    """
    return RateLimiter(rate_per_minute=get_settings().rate_limit_per_minute)


def reset_rate_limiter() -> None:
    """Clear the cached singleton (and its buckets) — test isolation only.

    Every actor gets a full bucket again on the next `get_rate_limiter()`
    call. Services' test `conftest.py` fixtures call this before each test
    so unrelated tests never share rate-limit state via the process-wide
    singleton.
    """
    get_rate_limiter.cache_clear()
