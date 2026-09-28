"""Regression guard for pre-release audit finding 25.

The L3 gateway called ``response.raise_for_status()`` inside ``except
httpx.HTTPError``, so *every* non-2xx became ``AiUnavailableError`` -> 503.
Core's 404 means "this tenant has no data for that period", which is the normal
state for a new tenant, so users were told the AI service was down when the
truthful answer was "nothing to report yet". Worse, the exception escaped before
``l3/service.py`` could reach its own abstention path, so the audit event, the
cached result, and the user-facing caveat were all unreachable.
"""

from __future__ import annotations

import httpx
import pytest

from ai_agent.core.exceptions import AiUnavailableError, AuthorizationError
from ai_agent.features.l3.gateway import HttpL3CoreGateway


def _gateway() -> HttpL3CoreGateway:
    return HttpL3CoreGateway(
        base_url="http://core.internal",
        bearer_token="token",
        tenant_slug="default",
    )


def _responder(
    status: int,
    payload: object = None,
    *,
    body: bytes | None = None,
) -> object:
    """A client stub whose single GET returns a fixed response."""

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def get(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", "http://core.internal/x")
            if body is not None:
                return httpx.Response(status, content=body, request=request)
            return httpx.Response(status, json=payload, request=request)

    return _Client()


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: object) -> None:
    monkeypatch.setattr(HttpL3CoreGateway, "_create_client", lambda self, _c=client: _c)


class TestNotFoundIsAbstentionNotOutage:
    @pytest.mark.parametrize(
        ("method", "path_fragment"),
        [
            ("get_payroll_cost_movement", "payroll-cost"),
            ("get_leave_pay_pairs", "leave-pay-correlation"),
            ("get_compliance_risk", "alerts/compliance"),
        ],
    )
    async def test_404_returns_no_data_instead_of_raising(
        self,
        monkeypatch: pytest.MonkeyPatch,
        method: str,
        path_fragment: str,
    ) -> None:
        # All three endpoints carried the same copy-pasted defect, so all three
        # are asserted. A fix to one path would not have caught the others.
        seen: list[str] = []

        class _Client:
            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            async def get(self, url: str, **kwargs: object) -> httpx.Response:
                seen.append(str(url))
                return httpx.Response(
                    404,
                    json={"type": "about:blank", "title": "Not Found"},
                    request=httpx.Request("GET", str(url)),
                )

        _patch_client(monkeypatch, _Client())

        result = await getattr(_gateway(), method)("2026-09-28")

        # The load-bearing assertion: empty data, NOT an exception.
        assert result == {}
        assert any(path_fragment in url for url in seen)

    async def test_404_does_not_surface_as_503_to_the_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Restates the previous test as the user-visible symptom, because "it
        # returns {}" is only meaningful if {} is what the service needs to
        # abstain rather than error.
        _patch_client(monkeypatch, _responder(404, {"detail": "not found"}))
        gateway = _gateway()

        result = await gateway.get_payroll_cost_movement("2026-09-28")

        # L3NarrativeService._gather_signals -> has_material_activity(kind, {}) is
        # False -> _persist_abstention(status="abstained"). A truthy payload
        # would be the failure mode here.
        assert not result


class TestRealOutagesStillRaise:
    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    async def test_5xx_raises_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        # The other half of the contract: only 404 is an abstention. A blanket
        # "never raise" fix would pass the 404 tests and silently swallow real
        # outages, which is strictly worse than the bug.
        _patch_client(monkeypatch, _responder(status, {"detail": "boom"}))
        gateway = _gateway()

        with pytest.raises(AiUnavailableError):
            await gateway.get_payroll_cost_movement("2026-09-28")

    async def test_unparseable_body_raises_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_client(monkeypatch, _responder(200, body=b"<html>not json</html>"))
        gateway = _gateway()

        with pytest.raises(AiUnavailableError):
            await gateway.get_payroll_cost_movement("2026-09-28")

    @pytest.mark.parametrize("status", [401, 403])
    async def test_auth_failures_raise_authorization_not_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        # A permission problem is not an outage. Reporting it as 503 rendered
        # "AI service is down" for a user who simply may not read payroll.
        _patch_client(monkeypatch, _responder(status, {"detail": "nope"}))
        gateway = _gateway()

        with pytest.raises(AuthorizationError):
            await gateway.get_payroll_cost_movement("2026-09-28")

    async def test_transport_failure_raises_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Client:
            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            async def get(self, *args: object, **kwargs: object) -> httpx.Response:
                raise httpx.ConnectError("connection refused")

        _patch_client(monkeypatch, _Client())
        gateway = _gateway()

        with pytest.raises(AiUnavailableError):
            await gateway.get_payroll_cost_movement("2026-09-28")


class TestSuccessUnchanged:
    async def test_returns_the_envelope_data_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The happy path must be untouched by the status-handling change.
        _patch_client(
            monkeypatch,
            _responder(200, {"success": True, "data": {"total": 42}}),
        )
        gateway = _gateway()

        result = await gateway.get_payroll_cost_movement("2026-09-28")

        assert result == {"total": 42}

    async def test_200_with_data_absent_yields_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, _responder(200, {"success": True}))
        gateway = _gateway()

        assert await gateway.get_payroll_cost_movement("2026-09-28") == {}
