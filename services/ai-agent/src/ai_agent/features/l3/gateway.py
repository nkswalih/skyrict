"""L3 Core gateway - read-only access to L3 HR/Payroll endpoints over HTTP.

The L3 feature owns no HR tables: every figure is computed from core's HTTP API.
The :class:`L3CoreGatewayPort` protocol is what engines depend on; tests fake it,
production binds :class:`HttpL3CoreGateway`.
"""

from __future__ import annotations

from typing import Protocol

import httpx
import structlog

from ai_agent.core.config import settings
from ai_agent.core.core_http import CoreHttpTransport
from ai_agent.core.exceptions import AiUnavailableError, AuthorizationError

logger = structlog.get_logger("ai_agent.l3_gateway")

# Returned when core has no data for the requested period. Empty on purpose: it
# is the same shape the envelope parser produces for a data-less body, so the
# service's existing `has_material_activity` check abstains without any
# special-casing here.
_NO_DATA: dict[str, object] = {}


class L3CoreGatewayPort(Protocol):
    """Read-only L3 HR queries, scoped by the caller's identity."""

    async def get_payroll_cost_movement(self, as_of: object) -> dict[str, object]: ...
    async def get_leave_pay_pairs(self, as_of: object) -> dict[str, object]: ...
    async def get_compliance_risk(self, as_of: object) -> dict[str, object]: ...


class HttpL3CoreGateway(CoreHttpTransport):
    """One request's gateway: forwards the user's JWT + tenant slug to core."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        tenant_slug: str,
    ) -> None:
        super().__init__(
            base_url=base_url,
            bearer_token=bearer_token,
            tenant_slug=tenant_slug,
            timeout_seconds=settings.INVENTORY_SERVICE_TIMEOUT_SECONDS,
        )

    async def get_payroll_cost_movement(self, as_of: object) -> dict[str, object]:
        return await self._get(
            "/api/v1/ai/hr/l3/payroll-cost",
            params={"as_of": str(as_of)},
        )

    async def get_leave_pay_pairs(self, as_of: object) -> dict[str, object]:
        return await self._get(
            "/api/v1/ai/hr/l3/leave-pay-correlation",
            params={"as_of": str(as_of)},
        )

    async def get_compliance_risk(self, as_of: object) -> dict[str, object]:
        # as_of is accepted for interface symmetry with the other two and is
        # deliberately not forwarded: the compliance endpoint reports current
        # risk and takes no period parameter. The interface exists so a caller
        # can treat all three L3 sources uniformly.
        del as_of
        return await self._get("/api/v1/ai/hr/alerts/compliance")

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """GET a core L3 endpoint and return its ``data`` object.

        Status handling is the whole point of this method, so it lives in one
        place. The three public methods used to carry identical copies of this
        logic, which is how the 404 defect below existed three times over.

        404 is NOT an outage. Core answers 404 when a tenant has no data for the
        requested period - the normal state for a new tenant, and a routine one
        at a period boundary. Converting that to a 503 told users the AI was
        down when the truthful answer was "nothing to report yet", and it did so
        by raising out of the gateway before the service could reach its own
        abstention path (``l3/service.py``: ``has_material_activity`` ->
        ``_persist_abstention``, which audits, caches, and returns a real
        user-facing caveat). See pre-release audit finding 25.

        401/403 is a caller-authorization problem, not an outage, so it maps to
        the typed authorization error the same way every other core gateway in
        this service already does, rather than to a 503 the UI renders as "AI
        service is down".

        Everything else - 5xx, other 4xx, transport failures, unparseable bodies -
        remains an outage and keeps raising ``AiUnavailableError`` so the
        caller's retry and circuit-breaker path still applies.
        """
        try:
            async with self._create_client() as client:
                response = await client.get(
                    f"{self._base_url}{path}",
                    params=params,
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            logger.warning("l3_gateway_unreachable", path=path)
            raise AiUnavailableError("Core service is temporarily unavailable") from exc

        status = response.status_code

        if status == 404:
            # Info, not warning: this is an expected answer, and logging it as a
            # warning would train operators to ignore the event that matters.
            logger.info("l3_gateway_no_data", path=path, status=status)
            return dict(_NO_DATA)

        if status in (401, 403):
            logger.warning("l3_gateway_forbidden", path=path, status=status)
            raise AuthorizationError("Not authorized to read HR or payroll data")

        if not response.is_success:
            logger.warning("l3_gateway_rejected", path=path, status=status)
            raise AiUnavailableError("Core service is temporarily unavailable")

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("l3_gateway_bad_body", path=path, status=status)
            raise AiUnavailableError("Core service returned an unusable response") from exc
        if not isinstance(payload, dict):
            logger.warning("l3_gateway_bad_shape", path=path, status=status)
            raise AiUnavailableError("Core service returned an unusable response")
        data = payload.get("data")
        return data if isinstance(data, dict) else dict(_NO_DATA)
