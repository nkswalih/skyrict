"""
Fixed-window rate limiting backed by Redis, with fail-open semantics.

The limiter is keyed by an arbitrary string (e.g. ``"register:1.2.3.4"``) and
counts hits within a fixed window (``timestamp // window``). When Redis is
unavailable or a Redis command fails, the limiter FAILS OPEN (allows the
request) so registration and CI flows are never blocked by infra problems.

Redis is only connected lazily on the first enforcement call, so importing
this module has no side effects.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from redis.asyncio import Redis

from identity.core.config import settings
from skyrict_common.exceptions import RateLimitExceededError, RateLimitUnavailableError

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

logger = structlog.get_logger("identity.rate_limit")


def _seconds_until_window_close(window_seconds: int) -> int:
    """Seconds until the current fixed window closes (same bucket math as the
    limiter), floored at 1 so ``Retry-After`` is always a positive integer."""
    now = int(time.time())
    step = max(window_seconds, 1)
    window_start = (now // step) * step
    return max(1, window_start + step - now)


class RateLimiter:
    """Fixed-window counter over Redis (fail-open on infra errors)."""

    def __init__(self, *, redis_client: AsyncRedis | None = None) -> None:
        self._client: AsyncRedis | None = redis_client

    async def _get_client(self) -> AsyncRedis:
        """Return the Redis client, constructing it on first use.

        Deliberately called from *inside* the try block in `is_allowed`. An
        unbuildable client - a malformed ``REDIS_URL``, an unimportable driver -
        is an infrastructure failure exactly like a dropped connection, and must
        honour ``RATE_LIMIT_FAIL_CLOSED`` rather than escaping as an unhandled
        500. A 500 is neither fail-open nor fail-closed: it happens to close,
        but only on the endpoint that happened to call the limiter, and it
        reports a server fault for what is a configuration error.
        """
        if self._client is None:
            self._client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._client

    async def is_allowed(self, *, key: str, limit: int, window_seconds: int) -> bool:
        """Return True when the key is within the limit for this window."""
        try:
            client = await self._get_client()
            window = int(time.time()) // max(window_seconds, 1)
            rl_key = f"rl:{key}:{window}"
            count = int(await client.incr(rl_key))
            if count == 1:
                await client.expire(rl_key, window_seconds + 1)
            return count <= limit
        except Exception as exc:  # fail-open, or fail-closed when RATE_LIMIT_FAIL_CLOSED
            if settings.RATE_LIMIT_FAIL_CLOSED:
                logger.warning("rate_limit_fail_closed", key=key, error=str(exc))
                raise RateLimitUnavailableError() from exc
            logger.warning("rate_limit_fail_open", key=key, error=str(exc))
            return True

    async def enforce(self, *, key: str, limit: int, window_seconds: int) -> None:
        """Raise RateLimitExceededError when the key exceeds the limit."""
        if not await self.is_allowed(key=key, limit=limit, window_seconds=window_seconds):
            # Generic message shared by every guarded endpoint (register,
            # login, ...) - never names the endpoint or the key, so it cannot
            # hint at what the caller was doing or which account was targeted.
            retry_after_seconds = _seconds_until_window_close(window_seconds)
            raise RateLimitExceededError(
                "Too many attempts. Try again later.",
                retry_after_seconds=retry_after_seconds,
            )


limiter = RateLimiter()
