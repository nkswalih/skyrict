"""Core finance-forecast refresh client (SKY-82 A4).

Thin HTTP client used by the weekly scheduler to trigger a tenant's revenue
forecast recompute on the core API. ``tenant_slug`` is carried on the request
so core's tenant resolution can route without extra headers; ``bearer_token``
is the system-agent token that lands with real tenant enumeration (the same
placeholder posture as the narrator gateway, SKY-63).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    import uuid


class CoreForecastRefreshClient:
    def __init__(self, *, base_url: str, bearer_token: str, tenant_slug: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._tenant_slug = tenant_slug
        self._client = httpx.AsyncClient(timeout=30)

    async def refresh(self, tenant_id: uuid.UUID) -> None:
        headers = {"Authorization": f"Bearer {self._bearer_token}"}
        response = await self._client.post(
            f"{self._base_url}/api/v1/finance/forecast/revenue/refresh",
            headers=headers,
            params={"tenant_id": str(tenant_id), "tenant_slug": self._tenant_slug},
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
