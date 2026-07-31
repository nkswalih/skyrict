"""Redis-backed caching layer — TTL-based, serialization-agnostic.

Provides a simple async cache interface backed by Redis.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger("{name}.cache")


class CacheService:
    """Async cache backed by Redis. Wraps aioredis for simple get/set/delete."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url
        self._client = None

    async def get_client(self):
        """Lazy-init Redis client."""
        if self._client is None:
            try:
                import aioredis
                self._client = aioredis.from_url(
                    self._redis_url or "redis://localhost:6379/0",
                    decode_responses=True,
                )
            except ImportError:
                logger.warning("aioredis not installed — cache disabled")
                return None
        return self._client

    async def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        client = await self.get_client()
        if client is None:
            return None
        raw = await client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set a value in cache with TTL."""
        client = await self.get_client()
        if client is None:
            return
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await client.set(key, serialized, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        """Delete a value from cache."""
        client = await self.get_client()
        if client is not None:
            await client.delete(key)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
