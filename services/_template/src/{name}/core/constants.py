"""Application-wide constants — single source of truth for magic values."""

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

# ---------------------------------------------------------------------------
# Problem type URIs (RFC 7807)
# ---------------------------------------------------------------------------
PROBLEM_BASE_URL = "https://api.skyrict.io/problems"

PROBLEM_TOKEN_EXPIRED = f"{PROBLEM_BASE_URL}/token-expired"
PROBLEM_TOKEN_INVALID = f"{PROBLEM_BASE_URL}/token-invalid"
PROBLEM_AUTHENTICATION_ERROR = f"{PROBLEM_BASE_URL}/authentication-error"
PROBLEM_AUTHORIZATION_ERROR = f"{PROBLEM_BASE_URL}/authorization-error"
PROBLEM_USER_NOT_FOUND = f"{PROBLEM_BASE_URL}/user-not-found"
PROBLEM_TENANT_NOT_FOUND = f"{PROBLEM_BASE_URL}/tenant-not-found"
PROBLEM_VALIDATION_ERROR = f"{PROBLEM_BASE_URL}/validation-error"
PROBLEM_RATE_LIMIT_EXCEEDED = f"{PROBLEM_BASE_URL}/rate-limit-exceeded"
PROBLEM_INTERNAL_ERROR = f"{PROBLEM_BASE_URL}/internal-error"

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
