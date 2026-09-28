"""Tenant-subdomain CORS wiring on the ai-agent app.

ai-agent is not in the public route map - core proxies to it server-to-server,
where CORS never applies. It already declares CORS configuration, so the policy
is wired here identically to identity and core rather than left to drift: three
copies of an origin policy that disagree is the failure mode that let the
published domain be wrong three times (see skyrict_common.problems for that
history).

The behaviour matrix is proven once in identity and once in core. This file
pins that ai-agent is not the odd one out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.middleware.cors import CORSMiddleware

from ai_agent.core.config import settings
from ai_agent.main import create_app

if TYPE_CHECKING:
    from fastapi import FastAPI

APEX = "https://skyrict.in"


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
