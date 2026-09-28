"""Application-wide constants - single source of truth for magic values."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# JWT / Token constants
# ---------------------------------------------------------------------------
ALGORITHM_RS256 = "RS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------
API_V1_PREFIX = "/api/v1"
SERVICE_NAME = "{name}"
SERVICE_VERSION = "0.1.0"

# NOTE: RFC 7807 problem types are NOT defined here. They used to be - a
# PROBLEM_BASE_URL literal plus 9 derived PROBLEM_* constants, none of which
# anything ever read, alongside a second, live copy in core/exceptions.py. Two
# definitions of one published contract is how the base drifted to a retired
# domain (pre-release audit finding 16). The base now lives in
# skyrict_common.problems, and core/exceptions.py is the only consumer. New
# services: add your exception to _STATUS_MAP there, not a constant here.

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS = 7
DEFAULT_TOKEN_EXPIRE_SECONDS = 1800
DEFAULT_PAGE_SIZE = 20
DEFAULT_RATE_LIMIT_LOGIN = 5
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 300

# ---------------------------------------------------------------------------
# Skip-auth paths (middleware bypass)
# ---------------------------------------------------------------------------
SKIP_AUTH_PATHS = frozenset({"/health", "/ready", "/docs", "/openapi.json", "/redoc"})
