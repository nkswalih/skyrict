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


class TestClientConstructionFailure:
    """An unbuildable Redis client must take the same path as a dropped one.

    `_get_client` used to be called *outside* the try block, so a construction
    failure escaped as an unhandled ValueError - a 500, which is neither
    fail-open nor fail-closed. It reported a server fault for what is a
    configuration error, and `RATE_LIMIT_FAIL_CLOSED` never saw it.

    These tests exercise the owning path (`RateLimiter()` with no injected
    client), which is the only one that constructs; the tests above all inject,
    so none of them reach it.
    """

    async def test_construction_failure_fails_open_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _explode(*_args: object, **_kwargs: object) -> None:
            raise ValueError("Redis URL must specify one of the following schemes")

        monkeypatch.setattr("identity.core.rate_limit.Redis.from_url", _explode)
        monkeypatch.setattr("identity.core.rate_limit.settings.RATE_LIMIT_FAIL_CLOSED", False)
        limiter = RateLimiter()

        assert await limiter.is_allowed(key="login:ip", limit=1, window_seconds=3600) is True

    async def test_construction_failure_fails_closed_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _explode(*_args: object, **_kwargs: object) -> None:
            raise ValueError("Redis URL must specify one of the following schemes")

        monkeypatch.setattr("identity.core.rate_limit.Redis.from_url", _explode)
        monkeypatch.setattr("identity.core.rate_limit.settings.RATE_LIMIT_FAIL_CLOSED", True)
        limiter = RateLimiter()

        with pytest.raises(RateLimitUnavailableError):
            await limiter.is_allowed(key="login:ip", limit=1, window_seconds=3600)

    async def test_a_second_call_reuses_the_constructed_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The client is built once and cached. Without this, every guarded
        # request would re-parse the URL and re-open a pool.
        builds: list[object] = []

        def _record(*args: object, **kwargs: object) -> FakeRedis:
            builds.append((args, kwargs))
            return FakeRedis()

        monkeypatch.setattr("identity.core.rate_limit.Redis.from_url", _record)
        limiter = RateLimiter()

        await limiter.is_allowed(key="a", limit=5, window_seconds=60)
        await limiter.is_allowed(key="a", limit=5, window_seconds=60)

        assert len(builds) == 1
