"""Tenant-subdomain CORS wiring on the core app.

core is the app the browser actually reaches for
/api/v1/ai/agents/chat/stream: the gateway route map sends the `ai` segment to
core, and core proxies onward to ai-agent. So core is where the agent chat
preflight has to succeed for the flagship demo to work at all.

The full behavioural matrix - every way the generated regex could over-match -
lives in services/identity/tests/unit/core/test_cors_origin_regex.py, because
all three services derive the identical policy from the identical helper. What
is asserted here is that core wires that policy, plus one positive and one
negative request so a regression in the wiring cannot pass silently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from core.core.config import settings
from core.main import create_app

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
        assert kwargs["allow_origins"] == [APEX]
        assert kwargs["allow_credentials"] is True

    def test_regex_degrades_to_none_when_base_domain_is_unusable(self, monkeypatch):
        monkeypatch.setattr(settings, "BASE_DOMAIN", "")
        monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])

        kwargs = _cors_kwargs(create_app())

        assert kwargs["allow_origin_regex"] is None
        assert kwargs["allow_origins"] == ["http://localhost:3000"]


class TestPreflightBehaviour:
    @pytest.fixture
    def client(self, monkeypatch) -> Iterator[TestClient]:
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.in")
        monkeypatch.setattr(settings, "CORS_ORIGINS", [APEX])
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
        response = self._preflight(client, TENANT)

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == TENANT
        assert response.headers["access-control-allow-credentials"] == "true"

    def test_foreign_origin_is_refused(self, client: TestClient):
        response = self._preflight(client, FOREIGN)

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    def test_tenant_actual_request_carries_the_origin_header(self, client: TestClient):
        response = client.post(CHAT_STREAM, headers={"Origin": TENANT})

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == TENANT
