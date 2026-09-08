"""L3 Core gateway - read-only access to L3 HR/Payroll endpoints over HTTP.

The L3 feature owns no HR tables: every figure is computed from core's HTTP API.
The :class:`L3CoreGatewayPort` protocol is what engines depend on; tests fake it,
production binds :class:`HttpL3CoreGateway`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

from ai_agent.core.config import settings
from ai_agent.core.exceptions import AiUnavailableError

logger = structlog.get_logger("ai_agent.l3_gateway")


class L3CoreGatewayPort(Protocol):
    """Read-only L3 HR queries, scoped by the caller's identity."""

    async def get_payroll_cost_movement(self, as_of: object) -> dict[str, object]: ...
    async def get_leave_pay_pairs(self, as_of: object) -> dict[str, object]: ...
    async def get_compliance_risk(self, as_of: object) -> dict[str, object]: ...


class HttpL3CoreGateway:
    """One request's gateway: forwards the user's JWT + tenant slug to core."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        tenant_slug: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._tenant_slug = tenant_slug

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._bearer_token}",
            "X-Tenant-Slug": self._tenant_slug,
        }

    async def get_payroll_cost_movement(self, as_of: object) -> dict[str, object]:
        params = {"as_of": str(as_of)}
        try:
            async with httpx.AsyncClient(
                timeout=settings.INVENTORY_SERVICE_TIMEOUT_SECONDS,
            ) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/ai/hr/l3/payroll-cost",
                    params=params,
                    headers=self._headers(),
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("l3_gateway_unreachable", path="/ai/hr/l3/payroll-cost")
            raise AiUnavailableError("Core service is temporarily unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("l3_gateway_bad_body", path="/ai/hr/l3/payroll-cost")
            raise AiUnavailableError("Core service returned an unusable response") from exc
        if not isinstance(payload, dict):
            raise AiUnavailableError("Core service returned an unusable response")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    async def get_leave_pay_pairs(self, as_of: object) -> dict[str, object]:
        params = {"as_of": str(as_of)}
        try:
            async with httpx.AsyncClient(
                timeout=settings.INVENTORY_SERVICE_TIMEOUT_SECONDS,
            ) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/ai/hr/l3/leave-pay-correlation",
                    params=params,
                    headers=self._headers(),
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("l3_gateway_unreachable", path="/ai/hr/l3/leave-pay-correlation")
            raise AiUnavailableError("Core service is temporarily unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("l3_gateway_bad_body", path="/ai/hr/l3/leave-pay-correlation")
            raise AiUnavailableError("Core service returned an unusable response") from exc
        if not isinstance(payload, dict):
            raise AiUnavailableError("Core service returned an unusable response")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    async def get_compliance_risk(self, as_of: object) -> dict[str, object]:
        raise NotImplementedError("C3 compliance-digest not yet wired")
