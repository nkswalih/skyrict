"""Domain exceptions -> RFC 7807 problem+json error responses.

Catch SkyrictError subclasses at the API layer and map to FastAPI responses
following https://www.rfc-editor.org/rfc/rfc7807 (Problem Details for HTTP APIs).
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from skyrict_common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    MFARequiredError,
    RateLimitExceededError,
    SkyrictError,
    TenantContextMissingError,
    TenantDisabledError,
    TenantNotFoundError,
    TokenExpiredError,
    TokenInvalidError,
    UserAlreadyExistsError,
    UserDisabledError,
    UserNotFoundError,
    ValidationError,
)

logger = logging.getLogger("{name}.exceptions")

_STATUS_MAP: dict[type, tuple[int, str]] = {
    TokenExpiredError: (401, "https://api.skyrict.io/problems/token-expired"),
    TokenInvalidError: (401, "https://api.skyrict.io/problems/token-invalid"),
    AuthenticationError: (401, "https://api.skyrict.io/problems/authentication-error"),
    AuthorizationError: (403, "https://api.skyrict.io/problems/authorization-error"),
    MFARequiredError: (403, "https://api.skyrict.io/problems/mfa-required"),
    UserNotFoundError: (404, "https://api.skyrict.io/problems/user-not-found"),
    TenantNotFoundError: (404, "https://api.skyrict.io/problems/tenant-not-found"),
    UserAlreadyExistsError: (409, "https://api.skyrict.io/problems/user-already-exists"),
    ValidationError: (422, "https://api.skyrict.io/problems/validation-error"),
    RateLimitExceededError: (429, "https://api.skyrict.io/problems/rate-limit-exceeded"),
    TenantDisabledError: (403, "https://api.skyrict.io/problems/tenant-disabled"),
    UserDisabledError: (403, "https://api.skyrict.io/problems/user-disabled"),
    TenantContextMissingError: (400, "https://api.skyrict.io/problems/tenant-context-missing"),
}


async def skyrict_error_handler(request: Request, exc: SkyrictError) -> JSONResponse:
    """Map SkyrictError to an RFC 7807 problem+json response."""
    status_code, problem_type = _STATUS_MAP.get(
        type(exc), (500, "https://api.skyrict.io/problems/internal-error")
    )

    body: dict = {
        "type": problem_type,
        "status": status_code,
        "title": exc.__class__.__name__,
        "detail": exc.message,
        "instance": getattr(request.state, "request_id", None),
    }

    return JSONResponse(status_code=status_code, content=body)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — NEVER leak internals."""
    request_id = getattr(request.state, "request_id", "unknown")
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
            "type": "https://api.skyrict.io/problems/internal-error",
            "status": 500,
            "title": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later.",
            "instance": request_id,
        },
    )
