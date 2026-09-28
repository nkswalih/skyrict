"""Application-wide constants - single source of truth for magic values."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------
API_V1_PREFIX = "/api/v1"
SERVICE_NAME = "ai-agent"
SERVICE_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# JWT constants
# ---------------------------------------------------------------------------
ALGORITHM_RS256 = "RS256"
TOKEN_TYPE_ACCESS = "access"

# NOTE: RFC 7807 problem types are NOT defined here. They used to be - a
# PROBLEM_BASE_URL literal plus 16 derived PROBLEM_* constants - alongside a
# second, live copy in core/exceptions.py. Two definitions of one published
# contract is how the base drifted to a retired domain (pre-release audit
# finding 16). The base now lives in skyrict_common.problems, and
# core/exceptions.py is the only consumer.

# ---------------------------------------------------------------------------
# Skip-auth paths (middleware bypass) - real mounted paths under /api/v1.
# ---------------------------------------------------------------------------
SKIP_AUTH_PATHS = frozenset(
    {
        f"{API_V1_PREFIX}/health",
        f"{API_V1_PREFIX}/ready",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)

# ---------------------------------------------------------------------------
# Multi-tenancy
# ---------------------------------------------------------------------------
# Platform-owned slugs never resolve to a tenant (mirrors core/identity). The
# routing contract is identical: Host subdomain in staging/production,
# X-Tenant-Slug header injected by nginx in dev/test.
RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "app",
        "blog",
        "docs",
        "dev",
        "help",
        "mail",
        "signin",
        "signup",
        "staging",
        "status",
        "support",
        "test",
        "web",
        "www",
        "acme",
        "skyrict",
    }
)
