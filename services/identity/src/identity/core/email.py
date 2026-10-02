"""Email delivery port and transports.

Two transports behind the same ``EmailService`` protocol:

* ``LogEmailService`` - logs the payload (default when no SMTP is configured).
* ``SmtpEmailService`` - delivers via SMTP using the stdlib (dev: Mailpit;
  prod: a real relay).

SMTP failures are logged but never raised, so auth flows don't hard-fail on
delivery problems. The SMTP transport never logs a credential (a real relay
must not leak codes). ``LogEmailService`` does log them, because that is the
whole point of the dev/test transport - but only in dev and test; see
``_logged_credential``.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

import structlog

from identity.core.config import Environment, settings
from identity.core.email_templates import (
    SecurityAlert,
    render_invitation_html,
    render_invitation_text,
    render_otp_html,
    render_otp_text,
    render_security_alert_html,
    render_security_alert_text,
)

logger = structlog.get_logger("identity.email")

# Environments where a log line is the delivery channel.
#
# Dev and test drive the signup wizard by reading the code back out of the log,
# so the cleartext value is the feature there. Staging and production are not:
# this transport is selected whenever EMAIL_SMTP_HOST is empty, which is exactly
# what a mis-provisioned relay looks like, and the failure mode of leaving the
# code in is an attacker reading a working credential out of the log stream.
#
# Redaction is keyed on ENVIRONMENT rather than on which transport was built,
# because "which transport" is the thing that silently degrades when config is
# wrong, and a guard that fails open on the exact failure it exists to catch is
# not a guard.
_CREDENTIAL_LOG_ENVIRONMENTS = frozenset({Environment.DEV, Environment.TEST})
_REDACTED = "[redacted]"


def _logged_credential(value: str) -> str:
    """Render a credential for a log line: cleartext in dev/test, redacted elsewhere."""
    if settings.ENVIRONMENT in _CREDENTIAL_LOG_ENVIRONMENTS:
        return value
    return _REDACTED


class EmailService(Protocol):
    """Delivery contract for transactional email."""

    async def send_otp(self, *, to: str, code: str) -> None: ...

    async def send_verification(
        self, *, to: str, full_name: str, token: str, base_url: str | None = None
    ) -> None: ...

    async def send_invitation(
        self,
        *,
        to: str,
        inviter_name: str,
        organization_name: str,
        token: str,
        base_url: str | None = None,
    ) -> None: ...

    async def send_security_alert(self, *, alert: SecurityAlert) -> None: ...


class LogEmailService:
    """Transport that logs the verification payload (dev/test default)."""

    async def send_otp(self, *, to: str, code: str) -> None:
        logger.info("email.otp.sent", to=to, otp_code=_logged_credential(code))

    async def send_verification(
        self, *, to: str, full_name: str, token: str, base_url: str | None = None
    ) -> None:
        """Record the verification email instead of sending it."""
        logger.info(
            "email.verification.sent",
            to=to,
            full_name=full_name,
            verification_token=_logged_credential(token),
            base_url=base_url,
        )

    async def send_invitation(
        self,
        *,
        to: str,
        inviter_name: str,
        organization_name: str,
        token: str,
        base_url: str | None = None,
    ) -> None:
        logger.info(
            "email.invitation.sent",
            to=to,
            inviter_name=inviter_name,
            organization_name=organization_name,
            invitation_token=_logged_credential(token),
            base_url=base_url,
        )

    async def send_security_alert(self, *, alert: SecurityAlert) -> None:
        logger.info(
            "email.security_alert.sent",
            to=alert.to,
            full_name=alert.full_name,
            event_type=alert.event_type,
            ip_address=alert.ip_address,
            location=alert.location,
            browser=alert.browser,
            os=alert.os,
            device=alert.device,
            auth_method=alert.auth_method,
            session_id_masked=alert.session_id_masked,
        )


class SmtpEmailService:
    """Transport that delivers transactional email over SMTP.

    Delivery runs in a thread so the event loop is never blocked by the
    (usually sub-millisecond) local relay round-trip. Failures are logged and
    swallowed - the OTP code is still retrievable in dev via the API response.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_addr: str,
        username: str = "",
        password: str = "",
        use_tls: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._from_addr = from_addr
        self._username = username
        self._password = password
        self._use_tls = use_tls

    async def send_otp(self, *, to: str, code: str) -> None:
        text = render_otp_text(code)
        html = render_otp_html(code)
        await self._deliver(to, "Your Skyrict verification code", text, html)

    async def send_verification(
        self, *, to: str, full_name: str, token: str, base_url: str | None = None
    ) -> None:
        if base_url:
            link = f"{base_url.rstrip('/')}?token={token}"
            text = (
                f"Hi {full_name},\n\nPlease verify your email address by "
                f"clicking the link below:\n\n{link}\n\n"
                "If you didn't create a Skyrict account, ignore this email."
            )
            html = (
                f"<p>Hi {full_name},</p><p>Please verify your email address by "
                f'clicking the link below:</p><p><a href="{link}">Verify '
                f"email</a></p>"
            )
        else:
            text = (
                f"Hi {full_name},\n\nYour Skyrict email verification token is "
                f"{token}.\n\nIt expires in 30 minutes."
            )
            html = (
                f"<p>Hi {full_name},</p><p>Your Skyrict email verification "
                f"token is <strong>{token}</strong>.</p>"
            )
        await self._deliver(to, "Verify your email address", text, html)

    async def send_invitation(
        self,
        *,
        to: str,
        inviter_name: str,
        organization_name: str,
        token: str,
        base_url: str | None = None,
    ) -> None:
        html = render_invitation_html(
            inviter_name=inviter_name,
            organization_name=organization_name,
            token=token,
            base_url=base_url,
        )
        text = render_invitation_text(
            inviter_name=inviter_name,
            organization_name=organization_name,
            token=token,
            base_url=base_url,
        )
        org = organization_name or "Skyrict"
        await self._deliver(
            to,
            f"{inviter_name} invited you to join {org} on Skyrict",
            text,
            html,
        )

    async def send_security_alert(self, *, alert: SecurityAlert) -> None:
        text = render_security_alert_text(alert)
        html = render_security_alert_html(alert)
        if alert.event_type == "new_device":
            subject = f"New login detected on your {alert.app_name} account"
        else:
            subject = f"Security alert: {alert.event_type}"
        await self._deliver(alert.to, subject, text, html)

    async def _deliver(self, to: str, subject: str, text: str, html: str | None) -> None:
        message = EmailMessage()
        message["From"] = self._from_addr
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        if html:
            message.add_alternative(html, subtype="html")

        def _blocking() -> None:
            with smtplib.SMTP(self._host, self._port, timeout=10) as client:
                client.ehlo()
                if self._use_tls:
                    client.starttls()
                    client.ehlo()
                if self._username:
                    client.login(self._username, self._password)
                client.send_message(message)

        try:
            await asyncio.to_thread(_blocking)
        except (OSError, smtplib.SMTPException) as exc:
            logger.exception(
                "email.delivery.failed",
                to=to,
                subject=subject,
                smtp_host=self._host,
                smtp_port=self._port,
                error=str(exc),
            )
            return
        logger.info("email.delivered", to=to, subject=subject)
