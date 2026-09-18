"""
Domain exceptions -> RFC 7807 problem+json error responses.

Catch SkyrictError subclasses at the API layer and map to FastAPI responses
following https://www.rfc-editor.org/rfc/rfc7807 (Problem Details for HTTP APIs).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from skyrict_common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    EmailNotVerifiedError,
    HandoffTokenAlreadyUsedError,
    HandoffTokenExpiredError,
    HandoffTokenNotFoundError,
    InvalidPasswordError,
    InvitationAlreadyUsedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    MFARequiredError,
    MFAVerificationError,
    NotFoundError,
    PasskeyError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitExceededError,
    RateLimitUnavailableError,
    SessionExpiredError,
    SessionNotFoundError,
    SkyrictError,
    TenantContextMissingError,
    TenantDisabledError,
    TenantMismatchError,
    TenantNotFoundError,
    TokenExpiredError,
    TokenInvalidError,
    TokenReuseDetectedError,
    UserAlreadyExistsError,
    UserDisabledError,
    UserNotFoundError,
    ValidationError,
)

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "EmailNotVerifiedError",
    "HandoffTokenAlreadyUsedError",
    "HandoffTokenExpiredError",
    "HandoffTokenNotFoundError",
    "InvalidPasswordError",
    "InvitationAlreadyUsedError",
    "InvitationEmailMismatchError",
    "InvitationExpiredError",
    "MFARequiredError",
    "MFAVerificationError",
    "NotFoundError",
    "PasskeyError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "RateLimitExceededError",
    "RateLimitUnavailableError",
    "SessionExpiredError",
    "SessionNotFoundError",
    "SkyrictError",
    "StartupError",
    "TenantContextMissingError",
    "TenantDisabledError",
    "TenantMismatchError",
    "TenantNotFoundError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TokenReuseDetectedError",
    "UserAlreadyExistsError",
    "UserDisabledError",
    "UserNotFoundError",
    "ValidationError",
]

logger = structlog.get_logger("identity.exceptions")


class StartupError(RuntimeError):
    """A required dependency failed startup verification.

    Raised from the application lifespan so the process refuses to boot
    (fail-fast) instead of serving traffic with a dead database, an
    unreachable Redis, or unusable JWT keys. NOT a SkyrictError - it is
    never mapped to an HTTP response; the orchestrator sees the non-zero
    exit and restarts the pod.
    """


_PROBLEM_BASE = "https://api.skyrict.io/problems"

# Mapping from exception type to HTTP status code and problem type URI.
# Lookup walks the MRO (exact type wins, base classes provide the generic
# fallback) so EVERY SkyrictError subclass maps to the correct status.
_STATUS_MAP: dict[type, tuple[int, str]] = {
    TokenExpiredError: (401, f"{_PROBLEM_BASE}/token-expired"),
    TokenInvalidError: (401, f"{_PROBLEM_BASE}/token-invalid"),
    TokenReuseDetectedError: (401, f"{_PROBLEM_BASE}/token-reuse-detected"),
    AuthenticationError: (401, f"{_PROBLEM_BASE}/authentication-error"),
    TenantMismatchError: (401, f"{_PROBLEM_BASE}/tenant-mismatch"),
    InvalidPasswordError: (401, f"{_PROBLEM_BASE}/invalid-password"),
    PasskeyError: (401, f"{_PROBLEM_BASE}/passkey-error"),
    SessionExpiredError: (401, f"{_PROBLEM_BASE}/session-expired"),
    AuthorizationError: (403, f"{_PROBLEM_BASE}/authorization-error"),
    PermissionDeniedError: (403, f"{_PROBLEM_BASE}/permission-denied"),
    PaymentRequiredError: (402, f"{_PROBLEM_BASE}/payment-required"),
    MFARequiredError: (403, f"{_PROBLEM_BASE}/mfa-required"),
    MFAVerificationError: (403, f"{_PROBLEM_BASE}/mfa-verification-error"),
    EmailNotVerifiedError: (403, f"{_PROBLEM_BASE}/email-not-verified"),
    TenantDisabledError: (403, f"{_PROBLEM_BASE}/tenant-disabled"),
    UserDisabledError: (403, f"{_PROBLEM_BASE}/user-disabled"),
    TenantContextMissingError: (400, f"{_PROBLEM_BASE}/tenant-context-missing"),
    NotFoundError: (404, f"{_PROBLEM_BASE}/not-found"),
    UserNotFoundError: (404, f"{_PROBLEM_BASE}/user-not-found"),
    TenantNotFoundError: (404, f"{_PROBLEM_BASE}/tenant-not-found"),
    SessionNotFoundError: (404, f"{_PROBLEM_BASE}/session-not-found"),
    ConflictError: (409, f"{_PROBLEM_BASE}/conflict"),
    UserAlreadyExistsError: (409, f"{_PROBLEM_BASE}/user-already-exists"),
    ValidationError: (422, f"{_PROBLEM_BASE}/validation-error"),
    RateLimitExceededError: (429, f"{_PROBLEM_BASE}/rate-limit-exceeded"),
    RateLimitUnavailableError: (503, f"{_PROBLEM_BASE}/rate-limit-unavailable"),
    InvitationExpiredError: (400, f"{_PROBLEM_BASE}/invitation-expired"),
    InvitationEmailMismatchError: (400, f"{_PROBLEM_BASE}/invitation-email-mismatch"),
    InvitationAlreadyUsedError: (409, f"{_PROBLEM_BASE}/invitation-already-used"),
    HandoffTokenExpiredError: (400, f"{_PROBLEM_BASE}/handoff-token-expired"),
    HandoffTokenNotFoundError: (404, f"{_PROBLEM_BASE}/handoff-token-not-found"),
    HandoffTokenAlreadyUsedError: (409, f"{_PROBLEM_BASE}/handoff-token-already-used"),
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

    # RFC 7807 required fields
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
        and isinstance(exc, RateLimitExceededError)
        and exc.retry_after_seconds is not None
    ):
        # Polling clients and the BFF relay use Retry-After to schedule the
        # next attempt instead of hammering the same bucket until it resets.
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
    request_id = _request_id(request) or "unknown"
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_msg=str(exc),
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        exc_info=True,  # full traceback in logs
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
