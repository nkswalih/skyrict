"""Unit tests for tenant resolution and cross-check logic in the api middleware.

Covers the pure functions (no DB): Host-subdomain derivation, environment-
dependent slug derivation (Host vs X-Tenant-Slug), the JWT-vs-routed tenant
cross-check (in features/auth/security.py), and the skip-path policy.
Middleware wiring against a real database is exercised by
tests/integration/api/test_tenant_isolation.py.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from identity.api.middleware import (
    derive_tenant_slug,
    is_tenant_required_path,
    resolve_tenant_slug_from_host,
)
from identity.core.config import Environment, settings
from identity.core.exceptions import TenantMismatchError
from identity.features.auth.security import cross_check_jwt_tenant, cross_check_routing_hint


def _make_request(headers: dict[str, str]) -> Request:
    """Build a minimal Starlette Request with the given headers."""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in headers.items()
        ],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


class TestResolveTenantSlugFromHost:
    def test_simple_subdomain(self):
        assert (
            resolve_tenant_slug_from_host("globex.skyrict.com", base_domain="skyrict.com")
            == "globex"
        )

    def test_uppercase_host_normalized(self):
        assert (
            resolve_tenant_slug_from_host("GLOBEX.Skyrict.COM", base_domain="skyrict.com")
            == "globex"
        )

    def test_host_with_port(self):
        assert (
            resolve_tenant_slug_from_host("globex.skyrict.com:443", base_domain="skyrict.com")
            == "globex"
        )

    def test_base_domain_with_leading_dot(self):
        assert (
            resolve_tenant_slug_from_host("globex.skyrict.com", base_domain=".skyrict.com")
            == "globex"
        )

    def test_apex_is_not_a_tenant(self):
        assert resolve_tenant_slug_from_host("skyrict.com", base_domain="skyrict.com") is None

    def test_wrong_domain_suffix(self):
        assert resolve_tenant_slug_from_host("acme.evil.com", base_domain="skyrict.com") is None

    def test_suffix_lookalike_rejected(self):
        # A host ending in .evil.com must never resolve through skyrict.com.
        assert (
            resolve_tenant_slug_from_host("evil.skyrict.com.evil.com", base_domain="skyrict.com")
            is None
        )

    def test_multi_label_subdomain_uses_first_label(self):
        assert resolve_tenant_slug_from_host("a.b.skyrict.com", base_domain="skyrict.com") == "a"

    def test_invalid_slug_characters_rejected(self):
        assert (
            resolve_tenant_slug_from_host("bad_underscore.skyrict.com", base_domain="skyrict.com")
            is None
        )

    def test_empty_host(self):
        assert resolve_tenant_slug_from_host("", base_domain="skyrict.com") is None

    def test_empty_base_domain(self):
        assert resolve_tenant_slug_from_host("acme.skyrict.com", base_domain="") is None


class TestDeriveTenantSlug:
    def test_dev_uses_x_tenant_slug(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        assert derive_tenant_slug(_make_request({"X-Tenant-Slug": "globex"})) == "globex"

    def test_dev_normalizes_case(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        assert derive_tenant_slug(_make_request({"X-Tenant-Slug": "Globex"})) == "globex"

    def test_dev_missing_header_unresolvable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        assert derive_tenant_slug(_make_request({})) is None

    def test_dev_invalid_header_value_unresolvable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        assert derive_tenant_slug(_make_request({"X-Tenant-Slug": "Bad Slug!"})) is None

    def test_production_uses_host_ignores_spoofed_header(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.com")
        request = _make_request({"X-Tenant-Slug": "evil", "Host": "globex.skyrict.com"})
        assert derive_tenant_slug(request) == "globex"

    def test_production_unresolvable_host(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.com")
        assert derive_tenant_slug(_make_request({"Host": "localhost:8000"})) is None

    def test_staging_uses_host(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.STAGING)
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.com")
        assert derive_tenant_slug(_make_request({"Host": "globex.skyrict.com"})) == "globex"


class TestCrossCheckJwtTenant:
    def test_match_passes(self):
        cross_check_jwt_tenant("tenant-aaa", "tenant-aaa")  # no raise

    def test_mismatch_raises(self):
        with pytest.raises(TenantMismatchError):
            cross_check_jwt_tenant("tenant-aaa", "tenant-bbb")

    def test_missing_jwt_claim_is_treated_as_mismatch(self):
        with pytest.raises(TenantMismatchError):
            cross_check_jwt_tenant(None, "tenant-aaa")


class TestCrossCheckRoutingHint:
    """The routing hint is cross-checked against the SIGNED token's tenant.

    This is the control that makes the shared-host X-Tenant-Slug fallback
    safe: the hint picks which tenant a request is ABOUT, and any disagreement
    with the credential is refused before tenant data is read.
    """

    def test_match_passes(self):
        cross_check_routing_hint("globex", "globex")  # no raise

    def test_mismatch_raises(self):
        # Credential for one tenant, naming another - a cross-tenant attempt.
        with pytest.raises(TenantMismatchError):
            cross_check_routing_hint("globex", "evil")

    def test_empty_tenant_slug_cannot_match(self):
        with pytest.raises(TenantMismatchError):
            cross_check_routing_hint("", "globex")


class TestIsTenantRequiredPath:
    def test_health_skipped(self):
        assert is_tenant_required_path("/api/v1/health") is False

    def test_ready_skipped(self):
        assert is_tenant_required_path("/api/v1/ready") is False

    def test_docs_skipped(self):
        assert is_tenant_required_path("/docs") is False

    def test_openapi_skipped(self):
        assert is_tenant_required_path("/openapi.json") is False

    def test_login_requires_tenant(self):
        assert is_tenant_required_path("/api/v1/auth/login") is True

    def test_signup_paths_skipped(self):
        for path in (
            "/api/v1/auth/signup/start",
            "/api/v1/auth/signup/send-code",
            "/api/v1/auth/signup/verify-code",
            "/api/v1/auth/signup/password",
            "/api/v1/auth/signup/captcha",
            "/api/v1/auth/signup/check-email",
            "/api/v1/auth/signup/check-slug",
            "/api/v1/auth/signup/organization",
        ):
            assert is_tenant_required_path(path) is False

    def test_users_me_requires_tenant(self):
        assert is_tenant_required_path("/api/v1/users/me") is True
