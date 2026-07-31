"""Event schemas for Skyrict domain events.

Each event model:
1. Inherits from `BaseEvent`
2. Sets `event_type` as a class-level constant
3. Adds domain-specific fields
"""

from __future__ import annotations

from datetime import datetime

from skyrict_events.base import BaseEvent


class UserCreated(BaseEvent):
    """Published when a new user is registered."""

    event_type: str = "identity.user.created"
    user_id: str
    email: str
    full_name: str | None = None


class UserUpdated(BaseEvent):
    """Published when a user profile is updated."""

    event_type: str = "identity.user.updated"
    user_id: str
    changes: dict[str, object] | None = None


class AuthLoginSuccess(BaseEvent):
    """Published on successful login."""

    event_type: str = "identity.auth.login_success"
    user_id: str
    ip_address: str | None = None
    user_agent: str | None = None


class AuthLoginFailed(BaseEvent):
    """Published on failed login attempt."""

    event_type: str = "identity.auth.login_failed"
    user_id: str | None = None
    reason: str = "invalid_credentials"
    ip_address: str | None = None


class TenantCreated(BaseEvent):
    """Published when a new tenant (organization) is created."""

    event_type: str = "identity.tenant.created"
    tenant_id: str
    name: str
    slug: str


class SessionCreated(BaseEvent):
    """Published when a user session is created."""

    event_type: str = "identity.session.created"
    user_id: str
    session_id: str
    ip_address: str | None = None


class SessionRevoked(BaseEvent):
    """Published when a user session is revoked."""

    event_type: str = "identity.session.revoked"
    user_id: str
    session_id: str
    reason: str | None = None


class MFASuccess(BaseEvent):
    """Published when MFA verification succeeds."""

    event_type: str = "identity.mfa.success"
    user_id: str
    method: str = "totp"


class MFAFailed(BaseEvent):
    """Published when MFA verification fails."""

    event_type: str = "identity.mfa.failed"
    user_id: str
    method: str = "totp"
    reason: str = "invalid_code"


__all__ = [
    "AuthLoginFailed",
    "AuthLoginSuccess",
    "MFAFailed",
    "MFASuccess",
    "SessionCreated",
    "SessionRevoked",
    "TenantCreated",
    "UserCreated",
    "UserUpdated",
]
