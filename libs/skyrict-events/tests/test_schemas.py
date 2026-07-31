from __future__ import annotations

from skyrict_events.schemas import (
    AuthLoginFailed,
    AuthLoginSuccess,
    MFASuccess,
    SessionCreated,
    TenantCreated,
    UserCreated,
)


class TestUserCreated:
    def test_default_event_type(self):
        event = UserCreated(user_id="u-1", email="a@b.com", tenant_id="t-1")
        assert event.event_type == "identity.user.created"
        assert event.user_id == "u-1"
        assert event.email == "a@b.com"


class TestAuthLoginFailed:
    def test_default_reason(self):
        event = AuthLoginFailed(tenant_id="t-1")
        assert event.event_type == "identity.auth.login_failed"
        assert event.reason == "invalid_credentials"


class TestAuthLoginSuccess:
    def test_with_ip(self):
        event = AuthLoginSuccess(user_id="u-1", ip_address="1.2.3.4", tenant_id="t-1")
        assert event.ip_address == "1.2.3.4"


class TestTenantCreated:
    def test_fields(self):
        event = TenantCreated(tenant_id="t-1", name="Acme", slug="acme")
        assert event.name == "Acme"
        assert event.slug == "acme"


class TestSessionCreated:
    def test_fields(self):
        event = SessionCreated(user_id="u-1", session_id="s-1", tenant_id="t-1")
        assert event.session_id == "s-1"


class TestMFASuccess:
    def test_default_method(self):
        event = MFASuccess(user_id="u-1", tenant_id="t-1")
        assert event.method == "totp"
