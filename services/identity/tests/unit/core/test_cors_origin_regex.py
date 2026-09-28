"""Tenant-subdomain CORS wiring on the identity app.

Finding 7 of the pre-release audit claimed the browser-direct agent chat SSE
would be blocked, and named the right cause (an exact-match origin list that
cannot enumerate dynamic tenant subdomains) but the wrong layer: it pointed at
the nginx gateway, which never applied an origin policy at all. The backends do
run Starlette's CORSMiddleware, and core - not ai-agent - is the app the browser
reaches for /api/v1/ai/agents/chat/stream, so the middleware is exactly where the
fix belongs.

These tests assert the wiring, then assert the resulting behaviour through a
real request, because "the regex matches" and "Starlette honours the regex
alongside allow_credentials" are separate claims and only the second one is the
fix. Starlette refuses a wildcard when credentials are enabled, so if the regex
were ignored the credentialed preflight would fail - which is the failure this
is testing against.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from identity.core.config import settings
from identity.main import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator

APEX = "https://skyrict.in"
TENANT = "https://acme.skyrict.in"
FOREIGN = "https://acme.attacker.example"
CHAT_STREAM = "/api/v1/ai/agents/chat/stream"


def _cors_kwargs(app: FastAPI) -> dict:
    """Return the kwargs the app actually handed to CORSMiddleware."""
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return dict(middleware.kwargs)
    pytest.fail("CORSMiddleware is not registered on the app")


class TestCorsWiring:
    def test_tenant_subdomain_regex_is_derived_from_base_domain(self, monkeypatch):
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.in")
        monkeypatch.setattr(settings, "CORS_ORIGINS", [APEX])

        kwargs = _cors_kwargs(create_app())

        assert kwargs["allow_origin_regex"] == r"^https://[a-z0-9-]+\.skyrict\.in$"
        # The apex stays on the exact-match list; the regex only adds tenants.
        assert kwargs["allow_origins"] == [APEX]
        # Credentials are what forbid a wildcard, so the regex is the only
        # possible way this passes - assert it so a future "*" is caught here.
        assert kwargs["allow_credentials"] is True

    def test_regex_degrades_to_none_when_base_domain_is_unusable(self, monkeypatch):
        """Local development has no BASE_DOMAIN. It must fall back to the
        exact-match list, not crash and not emit a broken pattern."""
        monkeypatch.setattr(settings, "BASE_DOMAIN", "")
        monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])

        kwargs = _cors_kwargs(create_app())

        assert kwargs["allow_origin_regex"] is None
        assert kwargs["allow_origins"] == ["http://localhost:3000"]


class TestPreflightBehaviour:
    """Drive the service's own middleware options through a real request."""

    @pytest.fixture
    def client(self, monkeypatch) -> Iterator[TestClient]:
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.in")
        monkeypatch.setattr(settings, "CORS_ORIGINS", [APEX])
        # A bare app carrying only this service's CORS options. The full app
        # cannot be used here because its tenant middleware answers before CORS
        # runs, which would test the wrong layer.
        app = FastAPI()
        app.add_middleware(CORSMiddleware, **_cors_kwargs(create_app()))

        @app.post(CHAT_STREAM)
        async def _stream() -> dict[str, str]:
            return {"ok": "true"}

        with TestClient(app) as test_client:
            yield test_client

    @staticmethod
    def _preflight(client: TestClient, origin: str):
        return client.options(
            CHAT_STREAM,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    def test_tenant_origin_preflight_is_allowed(self, client: TestClient):
        """The defect: on a tenant subdomain the preflight was rejected, so the
        browser never issued the chat stream and nothing logged a cause."""
        response = self._preflight(client, TENANT)

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == TENANT
        assert response.headers["access-control-allow-credentials"] == "true"
        assert "POST" in response.headers["access-control-allow-methods"]
        assert "authorization" in response.headers["access-control-allow-headers"].lower()

    def test_apex_origin_still_allowed(self, client: TestClient):
        response = self._preflight(client, APEX)

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == APEX

    def test_foreign_origin_is_refused(self, client: TestClient):
        response = self._preflight(client, FOREIGN)

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    def test_lookalike_suffix_origin_is_refused(self, client: TestClient):
        """The trailing anchor is the only thing stopping this."""
        response = self._preflight(client, "https://acme.skyrict.in.attacker.example")

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    def test_nested_subdomain_is_refused(self, client: TestClient):
        response = self._preflight(client, "https://a.b.skyrict.in")

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    def test_plaintext_tenant_origin_is_refused(self, client: TestClient):
        response = self._preflight(client, "http://acme.skyrict.in")

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    def test_tenant_actual_request_carries_the_origin_header(self, client: TestClient):
        """Not just the preflight: the credentialed POST/stream response must
        also carry the header, or the browser still discards the body."""
        response = client.post(CHAT_STREAM, headers={"Origin": TENANT})

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == TENANT
        assert response.headers["access-control-allow-credentials"] == "true"
