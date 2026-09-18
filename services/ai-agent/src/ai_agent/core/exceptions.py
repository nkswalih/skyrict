"""
Domain exceptions -> RFC 7807 problem+json error responses.

Catch SkyrictError subclasses at the API layer and map to FastAPI responses
following https://www.rfc-editor.org/rfc/rfc7807 (Problem Details for HTTP APIs).

Tenant error mapping (mirrors core):
  missing tenant context -> 400 tenant-context-missing
  token/routed tenant mismatch -> 401 tenant-mismatch
  unknown tenant slug -> 404 tenant-not-found
  disabled tenant -> 403 tenant-disabled

AI error contract (SKY-57) - deterministic and typed so callers (the core
monolith proxy and the frontend mock-fallback policy) can react safely:
  all configured providers unavailable -> 503 ai-unavailable
  every provider returned unparseable output -> 502 ai-invalid-response
  rate limit exceeded -> 429 ai-rate-limited
  request would send local-only data to a cloud provider -> 422 ai-data-residency

Provider failures are NEVER leaked to clients: exception text stays generic,
provider names/models travel only in structured logs.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_agent.core.constants import (
    PROBLEM_AI_DATA_RESIDENCY,
    PROBLEM_AI_INVALID_RESPONSE,
    PROBLEM_AI_RATE_LIMITED,
    PROBLEM_AI_UNAVAILABLE,
)
from skyrict_common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    SkyrictError,
    TenantContextMissingError,
    TenantDisabledError,
    TenantMismatchError,
    TenantNotFoundError,
    TokenExpiredError,
    TokenInvalidError,
    ValidationError,
)

__all__ = [
    "AiDataResidencyError",
    "AiInvalidResponseError",
    "AiRateLimitError",
    "AiUnavailableError",
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "SkyrictError",
    "StartupError",
    "TenantContextMissingError",
    "TenantDisabledError",
    "TenantMismatchError",
    "TenantNotFoundError",
    "TokenExpiredError",
    "TokenInvalidError",
    "ValidationError",
]


class StartupError(RuntimeError):
    """A required dependency failed startup verification.

    Raised from the application lifespan so the process refuses to boot
    (fail-fast) instead of serving traffic with a dead database or an unusable
    JWT public key. NOT a SkyrictError - it is never mapped to an HTTP
    response; the orchestrator sees the non-zero exit and restarts the pod.
    """


# ---------------------------------------------------------------------------
# AI error contract (SKY-57)
#
# Every AI failure mode maps to ONE typed exception with a stable problem type
# so the frontend can distinguish: successful result, low-confidence abstention
# (not an error - a normal response), provider failure, invalid provider
# response, permission failure, rate-limit failure.
# ---------------------------------------------------------------------------


class AiUnavailableError(SkyrictError):
    """All configured providers failed or no provider is configured (503).

    ``detail`` names the failure MODE, never provider internals - safe to
    return to clients. The frontend mock-fallback policy keys off this type.
    """

    message = "AI service is temporarily unavailable"
    code = "AI_UNAVAILABLE"


class AiInvalidResponseError(SkyrictError):
    """Providers responded but every response failed schema validation (502)."""

    message = "AI provider returned an unusable response"
    code = "AI_INVALID_RESPONSE"


class AiRateLimitError(SkyrictError):
    """A configured AI rate limit was exceeded (429)."""

    message = "AI rate limit exceeded - retry shortly"
    code = "AI_RATE_LIMITED"

    def __init__(self, *, retry_after_seconds: int | None = None) -> None:
        """Carry seconds-until-close so the API layer can emit ``Retry-After``."""
        super().__init__()
        self.retry_after_seconds = retry_after_seconds


class AiDataResidencyError(SkyrictError):
    """The request carries local-only data but no cleared provider exists (422).

    Data-residency rules (inventory AI spec §5.5): cost prices, sell prices,
    customer/supplier names and user IDs must never reach a cloud provider.
    The request is blocked BEFORE any provider call is made.
    """

    message = "Request blocked by data-residency policy"
    code = "AI_DATA_RESIDENCY"


_PROBLEM_BASE = "https://api.skyrict.io/problems"

# Mapping from exception type to HTTP status code and problem type URI.
# Lookup walks the MRO (exact type wins, base classes provide the generic
# fallback) so EVERY SkyrictError subclass maps to the correct status.
_STATUS_MAP: dict[type, tuple[int, str]] = {
    TokenExpiredError: (401, f"{_PROBLEM_BASE}/token-expired"),
    TokenInvalidError: (401, f"{_PROBLEM_BASE}/token-invalid"),
    AuthenticationError: (401, f"{_PROBLEM_BASE}/authentication-error"),
    TenantMismatchError: (401, f"{_PROBLEM_BASE}/tenant-mismatch"),
    AuthorizationError: (403, f"{_PROBLEM_BASE}/authorization-error"),
    PermissionDeniedError: (403, f"{_PROBLEM_BASE}/permission-denied"),
    TenantDisabledError: (403, f"{_PROBLEM_BASE}/tenant-disabled"),
    TenantContextMissingError: (400, f"{_PROBLEM_BASE}/tenant-context-missing"),
    ConflictError: (409, f"{_PROBLEM_BASE}/conflict"),
    NotFoundError: (404, f"{_PROBLEM_BASE}/not-found"),
    TenantNotFoundError: (404, f"{_PROBLEM_BASE}/tenant-not-found"),
    ValidationError: (422, f"{_PROBLEM_BASE}/validation-error"),
    # AI error contract (SKY-57).
    AiUnavailableError: (503, PROBLEM_AI_UNAVAILABLE),
    AiInvalidResponseError: (502, PROBLEM_AI_INVALID_RESPONSE),
    AiRateLimitError: (429, PROBLEM_AI_RATE_LIMITED),
    AiDataResidencyError: (422, PROBLEM_AI_DATA_RESIDENCY),
}

_DEFAULT_STATUS = (500, f"{_PROBLEM_BASE}/internal-error")


def _status_and_type(exc: SkyrictError) -> tuple[int, str]:
    """Resolve (status_code, problem_type) by walking the exception MRO."""
    for exc_type in type(exc).__mro__:
        if exc_type in _STATUS_MAP:
            return _STATUS_MAP[exc_type]
    return _DEFAULT_STATUS


def _request_id(request: Request) -> str | None:
    """Return the request_id attached by RequestIdMiddleware, if any."""
    return getattr(request.state, "request_id", None)


async def skyrict_error_handler(request: Request, exc: SkyrictError) -> JSONResponse:
    """Map SkyrictError to an RFC 7807 problem+json response."""
    status_code, problem_type = _status_and_type(exc)

    body: dict[str, Any] = {
        "type": problem_type,
        "status": status_code,
        "title": exc.__class__.__name__,
        "detail": exc.message,
        "instance": _request_id(request),
    }

    headers: dict[str, str] | None = None
    if (
        status_code == 429
        and isinstance(exc, AiRateLimitError)
        and exc.retry_after_seconds is not None
    ):
        headers = {"Retry-After": str(exc.retry_after_seconds)}

    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return FastAPI body-validation failures as RFC 7807 (422)."""
    errors = exc.errors()
    messages = [
        f"{'.'.join(str(loc) for loc in error.get('loc', ()))}: {error.get('msg', '')}"
        for error in errors
    ]

    body: dict[str, Any] = {
        "type": f"{_PROBLEM_BASE}/validation-error",
        "status": 422,
        "title": "Validation Error",
        "detail": "; ".join(messages) or "Request validation failed",
        "instance": _request_id(request),
        "errors": errors,
    }

    return JSONResponse(status_code=422, content=body)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Return route-level HTTP errors (404/405/...) as RFC 7807."""
    status_code = exc.status_code
    body: dict[str, Any] = {
        "type": f"{_PROBLEM_BASE}/http-{status_code}",
        "status": status_code,
        "title": str(exc.detail),
        "detail": str(exc.detail),
        "instance": _request_id(request),
    }

    return JSONResponse(status_code=status_code, content=body, headers=exc.headers)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions - NEVER leak internals.

    Logs full traceback for debugging, returns sanitized 500 to the client.
    """
    from ai_agent.core.logging import get_logger

    logger = get_logger("ai_agent.core.exceptions")
    request_id = _request_id(request) or "unknown"
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_msg=str(exc),
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "type": f"{_PROBLEM_BASE}/internal-error",
            "status": 500,
            "title": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later.",
            "instance": request_id,
        },
    )
