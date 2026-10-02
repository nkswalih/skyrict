"""Unit tests for the Turnstile server-side verifier.

These exist because a failed verification is otherwise undiagnosable: the
caller raises one generic ValidationError for every failure mode, so these
tests pin the only place the real reason is still visible.
"""

from __future__ import annotations

import json

import httpx
import pytest
import structlog

import identity.core.turnstile as turnstile_mod
from identity.core.config import Environment
from identity.core.logging import configure_identity_logging
from identity.core.turnstile import TurnstileVerifier


class FakeResponse:
    """Minimal stand-in for httpx.Response returning a fixed siteverify body."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeClient:
    """Records the siteverify call and replays a canned response."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.posts: list[dict] = []

    async def post(self, url: str, *, data: dict) -> FakeResponse:
        self.posts.append({"url": url, "data": data})
        return FakeResponse(self._payload)


@pytest.fixture(autouse=True)
def _isolate_turnstile_logger():
    """Swap the module logger for a fresh structlog proxy per test."""
    original = turnstile_mod.logger
    yield
    turnstile_mod.logger = original
    structlog.reset_defaults()


def _use_capturing_logger() -> None:
    configure_identity_logging(log_level="INFO", json_output=True)
    turnstile_mod.logger = structlog.get_logger("identity.turnstile")


def _last_log(capsys) -> dict:
    out = capsys.readouterr().out
    lines = [line for line in out.strip().splitlines() if line.strip()]
    assert lines, "no log output captured"
    return json.loads(lines[-1])


def _verifier(payload: dict, *, secret_key: str = "0xsecret") -> tuple:
    client = FakeClient(payload)
    return TurnstileVerifier(secret_key=secret_key, client=client), client


async def test_valid_token_verifies_and_sends_nothing_to_logs(capsys) -> None:
    _use_capturing_logger()
    verifier, client = _verifier({"success": True, "hostname": "signup.skyrict.in"})

    assert await verifier.verify("good-token") is True
    assert client.posts[0]["data"]["response"] == "good-token"
    assert client.posts[0]["url"] == turnstile_mod._TURNSTILE_VERIFY_URL


async def test_missing_token_is_logged_distinctly(capsys) -> None:
    """No token at all is a different fault than a refused challenge."""
    _use_capturing_logger()
    verifier, client = _verifier({"success": True})

    assert await verifier.verify(None) is False
    # A missing token must never reach Cloudflare.
    assert client.posts == []
    entry = _last_log(capsys)
    assert entry["event"] == "turnstile_token_missing"


async def test_rejection_logs_cloudflare_error_codes(capsys) -> None:
    """The reason a challenge failed exists nowhere else, so it must land here."""
    _use_capturing_logger()
    verifier, _ = _verifier(
        {
            "success": False,
            "error-codes": ["hostname-not-allowed"],
            "hostname": "signup.skyrict.in",
        }
    )

    assert await verifier.verify("bad-token") is False
    entry = _last_log(capsys)
    assert entry["event"] == "turnstile_verify_rejected"
    assert entry["error_codes"] == ["hostname-not-allowed"]
    assert entry["hostname"] == "signup.skyrict.in"


async def test_rejection_never_logs_the_token(capsys) -> None:
    """The token is single-use credential material; a rejection log would leak it."""
    _use_capturing_logger()
    verifier, _ = _verifier({"success": False, "error-codes": ["timeout-or-duplicate"]})

    assert await verifier.verify("super-secret-token-value") is False
    out = capsys.readouterr().out
    assert "super-secret-token-value" not in out
    assert "0xsecret" not in out


async def test_rejection_tolerates_missing_error_codes(capsys) -> None:
    """Cloudflare omits error-codes on some failures; that must not raise."""
    _use_capturing_logger()
    verifier, _ = _verifier({"success": False})

    assert await verifier.verify("bad-token") is False
    entry = _last_log(capsys)
    assert entry["event"] == "turnstile_verify_rejected"
    assert entry["error_codes"] == []


async def test_transport_failure_is_logged_and_fails_closed(monkeypatch) -> None:
    _use_capturing_logger()

    class ExplodingClient:
        async def post(self, url: str, *, data: dict):
            raise httpx.ConnectError("dns failure")

    verifier = TurnstileVerifier(secret_key="0xsecret", client=ExplodingClient())

    assert await verifier.verify("any-token") is False


async def test_unconfigured_secret_only_passes_in_dev_and_test(monkeypatch) -> None:
    """Fail-closed in staging/production: no secret means no verification."""
    monkeypatch.setattr(turnstile_mod.settings, "ENVIRONMENT", Environment.STAGING)
    verifier = TurnstileVerifier(secret_key="", client=FakeClient({}))

    assert await verifier.verify("any-token") is False

    monkeypatch.setattr(turnstile_mod.settings, "ENVIRONMENT", Environment.TEST)
    assert await verifier.verify("any-token") is True
