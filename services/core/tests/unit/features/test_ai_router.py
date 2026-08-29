"""Unit tests for ``/api/v1/ai`` route-parameter validation.

Path ids must be UUIDs BEFORE anything is forwarded: FastAPI rejects any
other shape with 422 and the upstream request target only ever embeds the
canonical hyphenated form — no traversal or metacharacters can reach
ai-agent (taint cut for the CodeQL SSRF finding). Permission dependencies
and the pooled client are overridden; transport behaviour lives in
test_ai_proxy.py.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.features.ai import router as ai_router


def _app_with_recorder(seen: list[httpx.Request]) -> TestClient:
    """App with auth deps stubbed and an upstream that records every call."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    app = FastAPI()
    app.include_router(ai_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_router._require_ai_invoke] = lambda: {"sub": "u1"}
    app.dependency_overrides[ai_router._require_inventory_read] = lambda: {"sub": "u1"}
    app.dependency_overrides[ai_router._require_inventory_write] = lambda: {"sub": "u1"}
    app.dependency_overrides[ai_router._require_inventory_ai_approve] = lambda: {"sub": "u1"}
    client_factory = lambda: httpx.AsyncClient(  # noqa: E731
        transport=httpx.MockTransport(handler), base_url="http://ai.test"
    )
    app.dependency_overrides[ai_router.get_ai_client] = client_factory
    return TestClient(app)


class TestProxyPathIdsAreUuids:
    def test_valid_uuid_forwarded_canonically(self) -> None:
        seen: list[httpx.Request] = []
        client = _app_with_recorder(seen)
        suggestion_id = str(uuid.uuid4())

        response = client.post(
            f"/api/v1/ai/suggestions/{suggestion_id.upper()}/approve",
            headers={"authorization": "Bearer tok"},
        )

        assert response.status_code == 200
        assert len(seen) == 1
        # Uppercase input reaches ai-agent in canonical lowercase form.
        assert seen[0].url.path == f"/api/v1/ai/suggestions/{suggestion_id}/approve"

    def test_anomaly_escalate_forwards_uuid(self) -> None:
        seen: list[httpx.Request] = []
        client = _app_with_recorder(seen)
        anomaly_id = uuid.uuid4()

        response = client.post(
            f"/api/v1/ai/anomalies/{anomaly_id}/escalate",
            headers={"authorization": "Bearer tok"},
        )

        assert response.status_code == 200
        assert seen[0].url.path == f"/api/v1/ai/anomalies/{anomaly_id}/escalate"

    @pytest.mark.parametrize(
        ("route_template", "bad_id"),
        [
            pytest.param("/api/v1/ai/suggestions/{}/approve", "not-a-uuid", id="garbage"),
            pytest.param("/api/v1/ai/suggestions/{}/reject", "x@evil.test", id="authority-like"),
            pytest.param("/api/v1/ai/anomalies/{}/resolve", "%2e%2eadmin", id="encoded-dots"),
            pytest.param(
                "/api/v1/ai/anomalies/{}/dismiss",
                "00000000-0000-0000-0000-00000000000g",
                id="hex-with-bad-digit",
            ),
        ],
    )
    def test_malformed_id_rejected_before_any_forward(
        self, route_template: str, bad_id: str
    ) -> None:
        seen: list[httpx.Request] = []
        client = _app_with_recorder(seen)

        response = client.post(route_template.format(bad_id))

        assert response.status_code == 422
        assert seen == [], "malformed id must never reach ai-agent"

    def test_dot_segment_traversal_never_reaches_upstream(self) -> None:
        """httpx normalizes ``..`` client-side, so the request dies with 404
        at the router — the point is that NOTHING reaches ai-agent."""
        seen: list[httpx.Request] = []
        client = _app_with_recorder(seen)

        response = client.post("/api/v1/ai/anomalies/../../admin/escalate")

        assert response.status_code in (404, 422)
        assert seen == []
