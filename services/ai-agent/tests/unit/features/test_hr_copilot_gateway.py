"""Unit tests for the HTTP HR gateway adapter (httpx MockTransport)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from ai_agent.core.exceptions import AiUnavailableError
from ai_agent.features.hr_copilot.gateway import HttpHrGateway

Handler = Callable[[httpx.Request], httpx.Response]


def _make_gateway(handler: Handler) -> tuple[HttpHrGateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def transport_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    gateway = HttpHrGateway(
        base_url="https://core.internal",
        bearer_token="user-token-123",
        tenant_slug="acme-corp",
    )
    gateway._create_client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        timeout=5, transport=httpx.MockTransport(transport_handler)
    )
    return gateway, seen


def _envelope(data: object) -> dict[str, Any]:
    return {"success": True, "data": data, "message": "ok"}


_OVERVIEW = {
    "total_headcount": 120,
    "trend": [],
    "departments": [
        {"department_name": "Engineering", "count": 40},
        {"department_name": "Sales", "count": 25},
    ],
    "tenure_bands": [{"band": "1-3", "count": 70}],
    "narrative": "Headcount grew 4% MoM.",
}

_TENURE = {
    "total_headcount": 120,
    "bands": [{"band": "1-3", "count": 70}],
    "narrative": "Tenure concentrated at 1-3 years.",
}

_POLICY = {
    "casual_days_per_year": 12,
    "sick_days_per_year": 8,
    "effective_from": "2026-01-01",
}


class TestForwarding:
    async def test_forwards_caller_token_and_tenant_slug(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope(_OVERVIEW))

        gateway, seen = _make_gateway(handler)
        await gateway.get_overview()

        assert seen[0].headers["Authorization"] == "Bearer user-token-123"
        assert seen[0].headers["X-Tenant-Slug"] == "acme-corp"
        assert seen[0].url.path == "/api/v1/ai/hr/overview"


class TestParsing:
    async def test_overview_parsed_into_aggregate_context(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope(_OVERVIEW))

        gateway, _ = _make_gateway(handler)
        ctx = await gateway.get_overview()

        assert ctx is not None
        assert ctx.total_headcount == 120
        assert ctx.departments == (("Engineering", 40), ("Sales", 25))
        assert ctx.tenure_bands == (("1-3", 70),)
        assert ctx.narrative == "Headcount grew 4% MoM."

    async def test_leave_policy_parsed(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope(_POLICY))

        gateway, seen = _make_gateway(handler)
        ctx = await gateway.get_leave_policy()

        assert ctx is not None
        assert ctx.casual_days_per_year == 12
        assert ctx.sick_days_per_year == 8
        assert ctx.effective_from == "2026-01-01"
        assert seen[0].url.path == "/api/v1/hr/leave/policy"


class TestDegradation:
    async def test_non_200_degrades_to_none(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json=_envelope(None))

        gateway, _ = _make_gateway(handler)
        assert await gateway.get_tenure() is None

    async def test_transport_error_maps_to_typed_503(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        gateway, _ = _make_gateway(handler)
        with pytest.raises(AiUnavailableError):
            await gateway.get_tenure()


_EMPLOYEE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "employee_number": "E001",
    "first_name": "Asha",
    "last_name": "Kumar",
    "job_title": "Engineer",
    "hire_date": "2022-05-01",
    "employment_status": "active",
    "email": "asha@acme.test",
    "phone": "+15551234567",
    "department_id": "22222222-2222-2222-2222-222222222222",
    # Core echoes compensation; the gateway must never carry it into the ref.
    "active_compensation": ["120000", "USD"],
}

_ATTRITION_L2 = {
    "generated_at": "2026-09-01T00:00:00Z",
    "model_version": "v1",
    "employees": [
        {
            "employee_id": "11111111-1111-1111-1111-111111111111",
            "employee_number": "E001",
            "name": "Asha Kumar",
            "department_name": "Engineering",
            "risk_band": "high",
            "score": 0.85,
            "confidence": 0.9,
            "factors": [{"label": "long tenure", "contribution": 0.4, "direction": "up"}],
            "acknowledged": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
        }
    ],
}


class TestEmployeesAndAttrition:
    async def test_list_employees_parsed_without_compensation(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope([_EMPLOYEE]))

        gateway, seen = _make_gateway(handler)
        employees = await gateway.list_employees()

        assert seen[0].url.path == "/api/v1/hr/employees"
        assert len(employees) == 1
        employee = employees[0]
        assert employee.id.hex == "11111111111111111111111111111111"
        assert employee.employee_number == "E001"
        assert employee.first_name == "Asha"
        assert employee.job_title == "Engineer"
        assert employee.employment_status == "active"
        # Sensitive compensation is deliberately not part of the ref.
        assert not hasattr(employee, "active_compensation")
        assert not hasattr(employee, "compensation")

    async def test_list_employees_degrades_to_empty_on_bad_body(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope({"not": "a list"}))

        gateway, _ = _make_gateway(handler)
        assert await gateway.list_employees() == []

    async def test_get_attrition_parses_l2_for_individual_holder(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope(_ATTRITION_L2))

        gateway, seen = _make_gateway(handler)
        risks = await gateway.get_attrition()

        assert seen[0].url.path == "/api/v1/ai/hr/attrition"
        assert risks is not None
        assert len(risks) == 1
        assert risks[0].name == "Asha Kumar"
        assert risks[0].risk_band == "high"
        assert risks[0].score == 0.85
        assert risks[0].factors == ("long tenure",)

    async def test_get_attrition_returns_none_when_core_denies_403(self) -> None:
        # A non-individual caller gets a 403 with an L1 aggregates body; the
        # gateway must treat it as "no individual access", not as risk data.
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={
                    "success": False,
                    "data": {"detail": "erp.hr.ai.individual required"},
                    "message": "erp.hr.ai.individual required",
                },
            )

        gateway, _ = _make_gateway(handler)
        assert await gateway.get_attrition() is None

    async def test_get_attrition_returns_empty_list_for_no_scored_rows(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope({"employees": []}))

        gateway, _ = _make_gateway(handler)
        assert await gateway.get_attrition() == []
