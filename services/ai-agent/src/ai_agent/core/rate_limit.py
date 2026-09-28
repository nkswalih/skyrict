"""
Fixed-window rate limiting for AI endpoints, backed by Redis.

Mirrors identity's ``identity.core.rate_limit`` (same Redis INCR fixed-window
idiom, same fail-open default) with two AI-specific differences:

- exhaustion raises :class:`AiRateLimitError` (typed 429 ``ai-rate-limited``
  problem type from the SKY-57 error contract, not identity's generic 429);
- infra failure under fail-closed mode raises :class:`AiUnavailableError`
  (the AI service cannot honor its guarantees without its limiter).

Enforcement lives HERE (single choke point inside the ai-agent) rather than at
the core proxy: every path that can burn LLM tokens goes through this module,
and core passes 429s through untouched. Keys are tenant-scoped strings such as
``ai:nl_query:{tenant_id}:{user_id}``; they never contain prompt content or PII.

Fail-open semantics: when Redis is unavailable the limiter ALLOWS requests so
an infrastructure blip cannot take AI features down; set
``AI_RATE_LIMIT_FAIL_CLOSED=true`` to invert this for strict deployments.
Redis is connected lazily on first enforcement - importing is side-effect free.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.config import settings
from ai_agent.core.exceptions import AiRateLimitError, AiUnavailableError

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

logger = structlog.get_logger("ai_agent.rate_limit")


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
        """Return the shared Redis client (created by core.redis).

        Deliberately called from *inside* the try block in `is_allowed`. An
        unusable client is an infrastructure failure exactly like a dropped
        connection, and must honour ``RATE_LIMIT_FAIL_CLOSED`` rather than
        escaping as an unhandled 500. A 500 is neither fail-open nor
        fail-closed: it happens to close, but only on the endpoint that
        happened to call the limiter, and it reports a server fault for what is
        a configuration error.
        """
        if self._client is None:
            # The service owns ONE shared Redis pool (core.redis), closed by
            # the lifespan at shutdown - the limiter must not create another.
            from ai_agent.core.redis import redis_client

            self._client = redis_client
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
        except Exception as exc:
            if settings.RATE_LIMIT_FAIL_CLOSED:
                logger.warning("rate_limit_fail_closed", key=key, error=str(exc))
                raise AiUnavailableError("AI service is temporarily unavailable") from exc
            logger.warning("rate_limit_fail_open", key=key, error=str(exc))
            return True

    async def enforce(self, *, key: str, limit: int, window_seconds: int) -> None:
        """Raise AiRateLimitError when the key exceeds the limit."""
        if not await self.is_allowed(key=key, limit=limit, window_seconds=window_seconds):
            raise AiRateLimitError(retry_after_seconds=_seconds_until_window_close(window_seconds))


limiter = RateLimiter()
