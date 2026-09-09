"""Unit tests for the HTTP report gateway adapter (httpx MockTransport)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from ai_agent.core.exceptions import (
    AiUnavailableError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from ai_agent.features.report_builder.gateway import HttpReportGateway


def _make_gateway(handler: Any) -> tuple[HttpReportGateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def transport_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)  # type: ignore[no-any-return]

    gateway = HttpReportGateway(
        base_url="https://core.internal",
        bearer_token="user-token-123",
        tenant_slug="acme-corp",
    )
    # Swap the client factory for one bound to the mock transport (mirrors
    # the production per-call client construction).
    gateway._create_client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        timeout=5, transport=httpx.MockTransport(transport_handler)
    )
    return gateway, seen


_DEFINITION = {
    "slug": "ar_aging",
    "module": "accounting",
    "title": "AR Aging",
    "description": None,
    "params": ["tenant_id", "as_of_date"],
    "dataset": "Open Invoices",
    "dimensions": ["aging bucket"],
    "measures": ["outstanding balance"],
}


def _envelope(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


class TestForwarding:
    async def test_forwards_caller_token_and_tenant_slug_on_list(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope([_DEFINITION]))

        gateway, seen = _make_gateway(handler)
        await gateway.list_definitions()

        assert seen[0].headers["Authorization"] == "Bearer user-token-123"
        assert seen[0].headers["X-Tenant-Slug"] == "acme-corp"
        assert seen[0].url.path == "/api/v1/reports"

    async def test_run_forwards_params_body(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_envelope(
                    {
                        "columns": ["invoice number"],
                        "rows": [{"invoice number": "INV-1"}],
                        "truncated": False,
                    }
                ),
            )

        gateway, seen = _make_gateway(handler)
        await gateway.run_report("ar_aging", {"as_of_date": "2026-08-31"})

        assert seen[0].url.path == "/api/v1/reports/ar_aging/run"
        assert json.loads(seen[0].read()) == {"params": {"as_of_date": "2026-08-31"}}


class TestParsing:
    async def test_list_parses_definitions(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope([_DEFINITION]))

        gateway, _ = _make_gateway(handler)
        definitions = await gateway.list_definitions()

        assert definitions[0].slug == "ar_aging"
        assert definitions[0].dataset == "Open Invoices"
        assert definitions[0].dimensions == ("aging bucket",)
        assert definitions[0].measures == ("outstanding balance",)

    async def test_run_parses_scalar_rows_only(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_envelope(
                    {
                        "columns": ["invoice number", "balance"],
                        "rows": [
                            {
                                "invoice number": "INV-1",
                                "balance": "1234.5000",
                                "nested": {"x": 1},
                                "flag": True,
                            }
                        ],
                        "truncated": False,
                    }
                ),
            )

        gateway, _ = _make_gateway(handler)
        run = await gateway.run_report("ar_aging", {"as_of_date": "2026-08-31"})

        assert run.columns == ["invoice number", "balance"]
        assert run.rows == [{"invoice number": "INV-1", "balance": "1234.5000"}]
        assert run.truncated is False

    async def test_create_parses_created_definition(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            body = request.read()
            assert b'"source_slug"' in body
            assert b'"sql"' not in body
            return httpx.Response(
                200,
                json=_envelope(
                    {"definition": dict(_DEFINITION, slug="my_aging"), "default_params": {}}
                ),
            )

        gateway, _ = _make_gateway(handler)
        created = await gateway.create_definition(
            slug="my_aging",
            title="My Aging",
            module="accounting",
            description=None,
            source_slug="ar_aging",
            params=["tenant_id", "as_of_date"],
            default_params={"as_of_date": "2026-08-31"},
        )

        assert created.definition.slug == "my_aging"
        assert created.default_params == {}


class TestErrors:
    async def test_transport_failure_maps_to_typed_503(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        gateway, _ = _make_gateway(handler)
        with pytest.raises(AiUnavailableError):
            await gateway.list_definitions()

    async def test_unusable_envelope_maps_to_typed_503(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>not the api</html>")

        gateway, _ = _make_gateway(handler)
        with pytest.raises(AiUnavailableError):
            await gateway.list_definitions()

    async def test_server_error_maps_to_typed_503(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"problem": "boom"})

        gateway, _ = _make_gateway(handler)
        with pytest.raises(AiUnavailableError):
            await gateway.list_definitions()

    async def test_created_422_maps_to_validation_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"problem": "not a seed slug"})

        gateway, _ = _make_gateway(handler)
        with pytest.raises(ValidationError):
            await gateway.create_definition(
                slug="x",
                title="X",
                module="accounting",
                description=None,
                source_slug="not_a_seed",
                params=["tenant_id"],
            )

    async def test_created_409_maps_to_conflict_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"problem": "slug taken"})

        gateway, _ = _make_gateway(handler)
        with pytest.raises(ConflictError):
            await gateway.create_definition(
                slug="x",
                title="X",
                module="accounting",
                description=None,
                source_slug="ar_aging",
                params=["tenant_id"],
            )

    async def test_run_404_maps_to_not_found(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"problem": "nope"})

        gateway, _ = _make_gateway(handler)
        with pytest.raises(NotFoundError):
            await gateway.run_report("missing", {})

    async def test_forbidden_maps_to_authorization_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"problem": "denied"})

        gateway, _ = _make_gateway(handler)
        with pytest.raises(AuthorizationError):
            await gateway.run_report("ar_aging", {})
