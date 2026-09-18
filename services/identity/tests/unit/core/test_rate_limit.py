"""Unit tests for the Redis-backed fixed-window rate limiter."""

from __future__ import annotations

import pytest

from identity.core.rate_limit import RateLimiter
from skyrict_common.exceptions import RateLimitExceededError, RateLimitUnavailableError


class FakeRedis:
    """In-memory incr/expire double for the limiter."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True


class BrokenRedis:
    """Redis double that always raises (infra failure)."""

    async def incr(self, key: str) -> int:
        raise ConnectionError("redis down")

    async def expire(self, key: str, seconds: int) -> bool:
        raise ConnectionError("redis down")


class TestRateLimiter:
    async def test_allows_within_limit(self) -> None:
        limiter = RateLimiter(redis_client=FakeRedis())
        assert await limiter.is_allowed(key="register:ip", limit=5, window_seconds=3600) is True

    async def test_blocks_when_over_limit(self) -> None:
        limiter = RateLimiter(redis_client=FakeRedis())
        for _ in range(5):
            assert await limiter.is_allowed(key="register:ip", limit=5, window_seconds=3600) is True
        assert await limiter.is_allowed(key="register:ip", limit=5, window_seconds=3600) is False

    async def test_enforce_raises_when_over_limit(self) -> None:
        limiter = RateLimiter(redis_client=FakeRedis())
        for _ in range(5):
            await limiter.enforce(key="register:ip", limit=5, window_seconds=3600)
        with pytest.raises(RateLimitExceededError):
            await limiter.enforce(key="register:ip", limit=5, window_seconds=3600)

    async def test_enforce_carries_positive_retry_after(self) -> None:
        limiter = RateLimiter(redis_client=FakeRedis())
        for _ in range(5):
            await limiter.enforce(key="register:ip", limit=5, window_seconds=60)
        with pytest.raises(RateLimitExceededError) as excinfo:
            await limiter.enforce(key="register:ip", limit=5, window_seconds=60)
        assert excinfo.value.retry_after_seconds is not None
        assert excinfo.value.retry_after_seconds > 0

    async def test_keys_are_isolated_by_identity(self) -> None:
        limiter = RateLimiter(redis_client=FakeRedis())
        assert await limiter.is_allowed(key="register:a", limit=1, window_seconds=3600) is True
        assert await limiter.is_allowed(key="register:b", limit=1, window_seconds=3600) is True
        assert await limiter.is_allowed(key="register:a", limit=1, window_seconds=3600) is False

    async def test_fail_open_when_redis_unavailable(self) -> None:
        limiter = RateLimiter(redis_client=BrokenRedis())
        assert await limiter.is_allowed(key="register:ip", limit=1, window_seconds=3600) is True

    async def test_fail_closed_raises_when_redis_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr("identity.core.rate_limit.settings.RATE_LIMIT_FAIL_CLOSED", True)
        limiter = RateLimiter(redis_client=BrokenRedis())
        with pytest.raises(RateLimitUnavailableError):
            await limiter.is_allowed(key="login:ip", limit=1, window_seconds=3600)

    async def test_enforce_propagates_fail_closed(self, monkeypatch) -> None:
        monkeypatch.setattr("identity.core.rate_limit.settings.RATE_LIMIT_FAIL_CLOSED", True)
        limiter = RateLimiter(redis_client=BrokenRedis())
        with pytest.raises(RateLimitUnavailableError):
            await limiter.enforce(key="login:ip", limit=1, window_seconds=3600)
