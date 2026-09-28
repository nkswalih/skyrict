"""Unit tests for the Redis-backed rate limiter.

Mirrors identity's test doubles: a dict-based ``FakeRedis`` exercising the
INCR/expire fixed-window logic, and a ``BrokenRedis`` that raises to simulate
infra failure (fail-open default vs fail-closed config).
"""

from __future__ import annotations

import pytest

from ai_agent.core.config import settings
from ai_agent.core.exceptions import AiRateLimitError, AiUnavailableError
from ai_agent.core.rate_limit import RateLimiter


class FakeRedis:
    """Minimal INCR/expire double over a plain dict."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True


class BrokenRedis:
    """Every call raises - simulates Redis being down."""

    async def incr(self, key: str) -> int:
        raise ConnectionError("redis down")

    async def expire(self, key: str, seconds: int) -> bool:
        raise ConnectionError("redis down")


def _make_limiter(client: object) -> RateLimiter:
    # Pre-injected client: the limiter must NOT touch the shared pool.
    limiter = RateLimiter()
    limiter._client = client  # type: ignore[assignment]
    return limiter


class TestFixedWindow:
    async def test_allows_up_to_limit_then_blocks(self) -> None:
        limiter = _make_limiter(FakeRedis())
        kwargs = {"key": "ai:nl_query:t-1:u-1", "limit": 3, "window_seconds": 60}

        for _ in range(3):
            assert await limiter.is_allowed(**kwargs) is True

        assert await limiter.is_allowed(**kwargs) is False

    async def test_enforce_raises_typed_rate_limit_error(self) -> None:
        limiter = _make_limiter(FakeRedis())

        # limit=10: calls 1-10 pass, call 11 must raise.
        with pytest.raises(AiRateLimitError) as exc_info:
            for _ in range(11):
                await limiter.enforce(key="ai:nl_query:t-1:u-2", limit=10, window_seconds=60)
        assert exc_info.value.code == "AI_RATE_LIMITED"

    async def test_enforce_carries_positive_retry_after(self) -> None:
        limiter = _make_limiter(FakeRedis())

        with pytest.raises(AiRateLimitError) as exc_info:
            for _ in range(11):
                await limiter.enforce(key="ai:nl_query:t-1:u-2", limit=10, window_seconds=60)
        assert exc_info.value.retry_after_seconds is not None
        assert exc_info.value.retry_after_seconds > 0


class TestFailOpen:
    async def test_redis_down_allows_requests_by_default(self) -> None:
        assert settings.RATE_LIMIT_FAIL_CLOSED is False
        limiter = _make_limiter(BrokenRedis())

        allowed = await limiter.is_allowed(key="ai:nl_query:t-2:u-1", limit=5, window_seconds=60)
        assert allowed is True

    async def test_redis_down_fail_closed_maps_to_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "RATE_LIMIT_FAIL_CLOSED", True)
        limiter = _make_limiter(BrokenRedis())

        with pytest.raises(AiUnavailableError) as exc_info:
            await limiter.is_allowed(key="ai:nl_query:t-2:u-2", limit=5, window_seconds=60)
        # Fail-closed maps to the typed 503 contract (AI_UNAVAILABLE), not 500.
        assert exc_info.value.code == "AI_UNAVAILABLE"


class TestSharedClientUnavailable:
    """An unusable shared pool must take the same path as a dropped one.

    `_get_client` used to be called *outside* the try block, so the import of
    the shared pool - and anything else raised while acquiring a client -
    escaped as an unhandled exception. A 500 is neither fail-open nor
    fail-closed: it happens to close, but only on the endpoint that happened to
    call the limiter, and it reports a server fault for what is a
    configuration error. `RATE_LIMIT_FAIL_CLOSED` never saw it.

    `_make_limiter` injects a client, so it cannot reach this path; these
    tests use the owning constructor.
    """

    @staticmethod
    def _unbuildable_shared_pool(
        monkeypatch: pytest.MonkeyPatch,
        error: Exception,
    ) -> None:
        """Make `from ai_agent.core.redis import redis_client` raise.

        Implemented as a module whose `__getattr__` raises, so the *import
        statement itself* fails. Storing a `property` on a module would not do:
        module attribute access returns the property object rather than
        invoking it, so the acquisition would silently succeed and both tests
        below would pass whether or not the code under test was correct.
        """
        import sys
        import types

        class _UnusablePool(types.ModuleType):
            def __getattr__(self, name: str) -> object:
                if name == "redis_client":
                    raise error
                raise AttributeError(name)

        monkeypatch.setitem(
            sys.modules, "ai_agent.core.redis", _UnusablePool("ai_agent.core.redis")
        )

    async def test_the_fake_actually_breaks_acquisition(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Guards the guard: without this, a fake that cannot fail would make the
        # two tests below pass unconditionally, and the mutation-proof of the
        # whole change would be worthless.
        self._unbuildable_shared_pool(monkeypatch, ValueError("unusable"))
        with pytest.raises(ValueError, match="unusable"):
            await RateLimiter()._get_client()

    async def test_unusable_pool_fails_open_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._unbuildable_shared_pool(monkeypatch, ValueError("Redis URL must specify a scheme"))
        monkeypatch.setattr(settings, "RATE_LIMIT_FAIL_CLOSED", False)
        limiter = RateLimiter()

        allowed = await limiter.is_allowed(key="ai:nl_query:t-3:u-1", limit=5, window_seconds=60)
        assert allowed is True

    async def test_unusable_pool_fail_closed_maps_to_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._unbuildable_shared_pool(monkeypatch, ValueError("Redis URL must specify a scheme"))
        monkeypatch.setattr(settings, "RATE_LIMIT_FAIL_CLOSED", True)
        limiter = RateLimiter()

        with pytest.raises(AiUnavailableError) as exc_info:
            await limiter.is_allowed(key="ai:nl_query:t-3:u-2", limit=5, window_seconds=60)
        assert exc_info.value.code == "AI_UNAVAILABLE"

    async def test_a_second_call_reuses_the_shared_pool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The shared pool is imported once and cached; without this, every
        # guarded request would re-resolve the module.
        limiter = _make_limiter(FakeRedis())
        kwargs = {"key": "ai:nl_query:t-4:u-1", "limit": 5, "window_seconds": 60}

        await limiter.is_allowed(**kwargs)
        client_after_first = limiter._client
        await limiter.is_allowed(**kwargs)

        assert limiter._client is client_after_first
