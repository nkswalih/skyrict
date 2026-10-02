"""Unit tests for the email transports (log vs SMTP)."""

from __future__ import annotations

import json
import smtplib

import pytest
import structlog

import identity.core.email as email_mod
from identity.core.config import Environment
from identity.core.email import LogEmailService, SmtpEmailService
from identity.core.email_templates import SecurityAlert
from identity.core.logging import configure_identity_logging


class FakeSMTP:
    """In-memory stand-in for smtplib.SMTP that records what it would send."""

    def __init__(self, *args, **kwargs) -> None:
        self.sent: list = []
        self.ehlos = 0
        self.tls = 0
        self.logins: list[tuple[str, str]] = []

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def ehlo(self) -> None:
        self.ehlos += 1

    def starttls(self) -> None:
        self.tls += 1

    def login(self, username: str, password: str) -> None:
        self.logins.append((username, password))

    def send_message(self, message) -> None:
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _isolate_email_logger() -> None:
    """Swap the module logger for a fresh structlog proxy per test.

    Structlog bound loggers capture the processor chain at first use, so each
    test replaces the module logger so it observes the config just installed.
    """
    original = email_mod.logger
    yield
    email_mod.logger = original
    structlog.reset_defaults()


def _service(**overrides) -> SmtpEmailService:
    kwargs: dict = {
        "host": "mailpit",
        "port": 1025,
        "from_addr": "Skyrict <no-reply@skyrict.dev>",
    }
    kwargs.update(overrides)
    return SmtpEmailService(**kwargs)


def _capture_json_line(capsys) -> dict:
    out = capsys.readouterr().out
    lines = [line for line in out.strip().splitlines() if line.strip()]
    assert lines, "no log output captured"
    return json.loads(lines[-1])


def _pin_environment(monkeypatch, environment: Environment) -> None:
    """Force ENVIRONMENT for one test.

    Pinned explicitly rather than inherited from the config default: the whole
    point of the redaction is which environments get it, so a test that passes
    only because the suite happens to default to DEV proves nothing about
    staging.
    """
    monkeypatch.setattr(email_mod.settings, "ENVIRONMENT", environment)


def _use_capturing_logger() -> None:
    configure_identity_logging(log_level="INFO", json_output=True)
    email_mod.logger = structlog.get_logger("identity.email")


async def test_smtp_service_sends_otp_with_code(monkeypatch) -> None:
    fake = FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: fake)

    await _service().send_otp(to="alice@test.com", code="123456")

    assert len(fake.sent) == 1
    message = fake.sent[0]
    assert message["To"] == "alice@test.com"
    assert message["From"] == "Skyrict <no-reply@skyrict.dev>"
    plain = message.get_body(preferencelist=("plain",))
    assert plain is not None
    assert "1 2 3 4 5 6" in plain.get_content()
    # Multipart alternative includes an HTML variant.
    assert message.get_body(preferencelist=("html",)) is not None


async def test_smtp_service_applies_tls_and_auth(monkeypatch) -> None:
    fake = FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: fake)

    await _service(username="user", password="secret", use_tls=True).send_otp(
        to="bob@test.com", code="654321"
    )

    assert fake.tls == 1
    assert fake.logins == [("user", "secret")]
    assert len(fake.sent) == 1


async def test_smtp_service_swallows_delivery_failure(monkeypatch, capsys) -> None:
    def _raising(*args, **kwargs) -> None:
        raise smtplib.SMTPConnectError(421, b"service not available")

    monkeypatch.setattr(smtplib, "SMTP", _raising)
    configure_identity_logging(log_level="INFO", json_output=True)
    email_mod.logger = structlog.get_logger("identity.email")

    # Must not raise - auth flows tolerate a dead relay.
    await _service().send_otp(to="carol@test.com", code="000000")

    parsed = _capture_json_line(capsys)
    assert parsed["event"] == "email.delivery.failed"
    assert parsed["to"] == "carol@test.com"


async def test_log_service_logs_otp_code_in_dev(monkeypatch, capsys) -> None:
    _pin_environment(monkeypatch, Environment.DEV)
    _use_capturing_logger()

    await LogEmailService().send_otp(to="dave@test.com", code="112233")

    parsed = _capture_json_line(capsys)
    assert parsed["event"] == "email.otp.sent"
    assert parsed["otp_code"] == "112233"
    assert parsed["to"] == "dave@test.com"


async def test_log_service_logs_otp_code_in_test(monkeypatch, capsys) -> None:
    _pin_environment(monkeypatch, Environment.TEST)
    _use_capturing_logger()

    await LogEmailService().send_otp(to="dave@test.com", code="112233")

    assert _capture_json_line(capsys)["otp_code"] == "112233"


@pytest.mark.parametrize(
    "environment",
    [Environment.STAGING, Environment.PRODUCTION],
)
async def test_log_service_redacts_otp_code_outside_dev_test(
    monkeypatch, capsys, environment: Environment
) -> None:
    _pin_environment(monkeypatch, environment)
    _use_capturing_logger()

    await LogEmailService().send_otp(to="dave@test.com", code="112233")

    parsed = _capture_json_line(capsys)
    # The fact that mail was sent, and to whom, still has to be observable -
    # the recipient is what makes a signup supportable.
    assert parsed["event"] == "email.otp.sent"
    assert parsed["to"] == "dave@test.com"
    assert parsed["otp_code"] == "[redacted]"
    # The value must be absent from the line, not merely altered.
    assert "112233" not in json.dumps(parsed)


@pytest.mark.parametrize(
    "environment",
    [Environment.STAGING, Environment.PRODUCTION],
)
async def test_log_service_redacts_link_tokens_outside_dev_test(
    monkeypatch, capsys, environment: Environment
) -> None:
    _pin_environment(monkeypatch, environment)
    _use_capturing_logger()
    service = LogEmailService()

    await service.send_verification(to="frank@test.com", full_name="Frank", token="verify-secret")
    verification = _capture_json_line(capsys)

    await service.send_invitation(
        to="gina@test.com",
        inviter_name="Gina",
        organization_name="Acme",
        token="invite-secret",
    )
    invitation = _capture_json_line(capsys)

    assert verification["verification_token"] == "[redacted]"
    assert invitation["invitation_token"] == "[redacted]"
    assert "verify-secret" not in json.dumps(verification)
    assert "invite-secret" not in json.dumps(invitation)


async def test_smtp_service_sends_security_alert_with_html(monkeypatch) -> None:
    fake = FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: fake)

    await _service().send_security_alert(
        alert=SecurityAlert(
            to="erin@test.com",
            full_name="Erin User",
            event_type="new_device",
            ip_address="203.0.113.***",
            location="Bengaluru, Karnataka, India",
            browser="Chrome 126",
            os="Windows 11",
            device="Unknown (Desktop)",
            auth_method="Password + MFA",
            session_id_masked="3f9a2c1d••••",
            date_time="Aug 8, 2026 at 2:07 PM UTC",
        )
    )

    assert len(fake.sent) == 1
    message = fake.sent[0]
    assert message["To"] == "erin@test.com"
    assert message["Subject"] == "New login detected on your Skyrict account"

    plain = message.get_body(preferencelist=("plain",))
    assert plain is not None
    assert "New login detected" in plain.get_content()

    html = message.get_body(preferencelist=("html",))
    assert html is not None
    body = html.get_content()
    assert "<!DOCTYPE html>" in body
    assert "New login detected" in body
    assert "203.0.113.***" in body


async def test_log_service_logs_security_alert_details(capsys) -> None:
    configure_identity_logging(log_level="INFO", json_output=True)
    email_mod.logger = structlog.get_logger("identity.email")

    await LogEmailService().send_security_alert(
        alert=SecurityAlert(
            to="erin@test.com",
            full_name="Erin User",
            event_type="new_device",
            ip_address="203.0.113.***",
            location="Bengaluru, Karnataka, India",
            browser="Chrome 126",
            os="Windows 11",
            device="Unknown (Desktop)",
            auth_method="Password + MFA",
            session_id_masked="3f9a2c1d••••",
            date_time="Aug 8, 2026 at 2:07 PM UTC",
        )
    )

    parsed = _capture_json_line(capsys)
    assert parsed["event"] == "email.security_alert.sent"
    assert parsed["ip_address"] == "203.0.113.***"
    assert parsed["location"] == "Bengaluru, Karnataka, India"
    assert parsed["browser"] == "Chrome 126"
