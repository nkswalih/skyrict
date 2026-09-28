"""Unit tests for the centralized tenant resolver (identity/core/tenant_resolver.py).

Covers the pure functions (no DB): Host-subdomain derivation with reserved/
platform slug handling, X-Tenant-Slug derivation in dev, and the
environment-dependent resolution used by the middleware.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request

from identity.core.config import Environment, settings
from identity.core.constants import RESERVED_SLUGS
from identity.core.tenant_resolver import (
    TenantResolver,
    derive_tenant_slug,
    resolve_tenant_slug_from_host,
)

if TYPE_CHECKING:
    import pytest


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


class TestReservedSlugsCatalog:
    def test_contains_all_platform_hostnames(self):
        expected = {
            "web",
            "signup",
            "signin",
            "admin",
            "api",
            "www",
            "app",
            "docs",
            "status",
            "mail",
            "support",
            "help",
            "blog",
            "dev",
            "test",
            "staging",
            "acme",
            "skyrict",
        }
        assert expected <= RESERVED_SLUGS


class TestResolveTenantSlugFromHost:
    def test_plain_tenant_subdomain(self):
        assert (
            resolve_tenant_slug_from_host("globex.skyrict.com", base_domain="skyrict.com")
            == "globex"
        )

    def test_reserved_slug_never_resolves(self):
        for slug in ("web", "app", "admin", "signup", "signin", "api", "www", "acme"):
            assert (
                resolve_tenant_slug_from_host(f"{slug}.skyrict.com", base_domain="skyrict.com")
                is None
            ), f"{slug}.skyrict.com must not resolve as a tenant"

    def test_reserved_slug_second_label_still_never_resolves(self):
        # Even a tenant-looking host whose first label is reserved is a platform
        # surface (e.g. api.skyrict.com), never a tenant subdomain.
        assert (
            resolve_tenant_slug_from_host("api.extra.skyrict.com", base_domain="skyrict.com")
            is None
        )

    def test_apex_is_not_a_tenant(self):
        assert resolve_tenant_slug_from_host("skyrict.com", base_domain="skyrict.com") is None

    def test_wrong_domain_suffix(self):
        assert resolve_tenant_slug_from_host("acme.evil.com", base_domain="skyrict.com") is None

    def test_host_with_port_still_reserved(self):
        assert (
            resolve_tenant_slug_from_host("web.skyrict.com:443", base_domain="skyrict.com") is None
        )

    def test_empty_host(self):
        assert resolve_tenant_slug_from_host("", base_domain="skyrict.com") is None

    def test_empty_base_domain(self):
        assert resolve_tenant_slug_from_host("acme.skyrict.com", base_domain="") is None


class TestTenantResolverFromHeader:
    def test_plain_slug(self):
        assert TenantResolver(base_domain="skyrict.com").resolve_from_header("globex") == "globex"

    def test_case_normalized(self):
        assert TenantResolver(base_domain="skyrict.com").resolve_from_header("Globex") == "globex"

    def test_reserved_slug_rejected(self):
        for slug in ("web", "admin", "skyrict", "docs"):
            assert TenantResolver(base_domain="skyrict.com").resolve_from_header(slug) is None

    def test_invalid_slug_rejected(self):
        assert TenantResolver(base_domain="skyrict.com").resolve_from_header("Bad Slug!") is None

    def test_missing_slug(self):
        assert TenantResolver(base_domain="skyrict.com").resolve_from_header(None) is None
        assert TenantResolver(base_domain="skyrict.com").resolve_from_header("") is None


class TestTenantResolverResolve:
    def test_dev_uses_x_tenant_slug(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        request = _make_request({"X-Tenant-Slug": "globex", "Host": "localhost:8000"})
        assert TenantResolver(base_domain="skyrict.com").resolve(request) == "globex"

    def test_dev_reserved_slug_unresolvable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        request = _make_request({"X-Tenant-Slug": "web"})
        assert TenantResolver(base_domain="skyrict.com").resolve(request) is None

    def test_production_uses_host_ignores_spoofed_header(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        request = _make_request({"X-Tenant-Slug": "evil", "Host": "globex.skyrict.com"})
        assert TenantResolver(base_domain="skyrict.com").resolve(request) == "globex"

    def test_production_reserved_host_unresolvable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        request = _make_request({"X-Tenant-Slug": "acme", "Host": "www.skyrict.com"})
        assert TenantResolver(base_domain="skyrict.com").resolve(request) is None

    def test_production_unresolvable_host(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        request = _make_request({"Host": "localhost:8000"})
        assert TenantResolver(base_domain="skyrict.com").resolve(request) is None


class TestDeriveTenantSlug:
    def test_dev_uses_header(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        assert derive_tenant_slug(_make_request({"X-Tenant-Slug": "globex"})) == "globex"

    def test_dev_reserved_header_unresolvable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        assert derive_tenant_slug(_make_request({"X-Tenant-Slug": "support"})) is None

    def test_production_reserved_host_unresolvable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.com")
        assert derive_tenant_slug(_make_request({"Host": "blog.skyrict.com"})) is None

    def test_staging_uses_host(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.STAGING)
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.com")
        assert derive_tenant_slug(_make_request({"Host": "globex.skyrict.com"})) == "globex"


class TestSharedApiHostFallback:
    """Production serves every service from ONE host (api.skyrict.in).

    That host has no tenant label, and "api" is a reserved slug, so the Host
    yields nothing. The X-Tenant-Slug hint the BFF already sends is what makes
    the shared host routable. These tests pin that fallback - it is routing
    only, and the middleware independently derives the tenant from the verified
    JWT and cross-checks this hint, so a forged value cannot grant access.
    """

    def test_shared_api_host_falls_back_to_header(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        resolver = TenantResolver(base_domain="skyrict.in")
        request = _make_request({"Host": "api.skyrict.in", "X-Tenant-Slug": "globex"})
        assert resolver.resolve(request) == "globex"

    def test_shared_api_host_without_header_is_unresolvable(self, monkeypatch: pytest.MonkeyPatch):
        # None here is correct, not a failure: an authenticated request on a
        # shared host resolves its tenant from the JWT instead of the Host.
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        resolver = TenantResolver(base_domain="skyrict.in")
        request = _make_request({"Host": "api.skyrict.in"})
        assert resolver.resolve(request) is None

    def test_aca_default_fqdn_falls_back_to_header(self, monkeypatch: pytest.MonkeyPatch):
        # The pre-custom-domain host is not a subdomain of BASE_DOMAIN at all.
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        resolver = TenantResolver(base_domain="skyrict.in")
        request = _make_request(
            {
                "Host": "app-identity-skyrict-beta.eastus.azurecontainerapps.io",
                "X-Tenant-Slug": "globex",
            }
        )
        assert resolver.resolve(request) == "globex"

    def test_per_tenant_host_still_wins_over_header(self, monkeypatch: pytest.MonkeyPatch):
        # A valid header must NOT be able to redirect a request that arrived on
        # a specific tenant's host - that is the anti-spoofing property.
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        resolver = TenantResolver(base_domain="skyrict.in")
        request = _make_request({"Host": "globex.skyrict.in", "X-Tenant-Slug": "evil"})
        assert resolver.resolve(request) == "globex"

    def test_reserved_hint_still_rejected_on_shared_host(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        resolver = TenantResolver(base_domain="skyrict.in")
        request = _make_request({"Host": "api.skyrict.in", "X-Tenant-Slug": "api"})
        assert resolver.resolve(request) is None

    def test_malformed_hint_still_rejected_on_shared_host(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        resolver = TenantResolver(base_domain="skyrict.in")
        request = _make_request({"Host": "api.skyrict.in", "X-Tenant-Slug": "Bad Slug!"})
        assert resolver.resolve(request) is None

    def test_staging_shares_the_fallback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.STAGING)
        resolver = TenantResolver(base_domain="skyrict.in")
        request = _make_request({"Host": "api.skyrict.in", "X-Tenant-Slug": "globex"})
        assert resolver.resolve(request) == "globex"

    def test_derive_tenant_slug_on_shared_host(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
        monkeypatch.setattr(settings, "BASE_DOMAIN", "skyrict.in")
        request = _make_request({"Host": "api.skyrict.in", "X-Tenant-Slug": "globex"})
        assert derive_tenant_slug(request) == "globex"
