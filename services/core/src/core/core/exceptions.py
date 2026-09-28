"""
Domain exceptions -> RFC 7807 problem+json error responses.

Catch SkyrictError subclasses at the API layer and map to FastAPI responses
following https://www.rfc-editor.org/rfc/rfc7807 (Problem Details for HTTP APIs).

Tenant error mapping (ERP-FND-001):
  missing tenant context -> 400 tenant-context-missing
  token/routed tenant mismatch -> 401 tenant-mismatch
  unknown tenant slug -> 404 tenant-not-found
  disabled tenant -> 403 tenant-disabled
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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
from skyrict_common.problems import PROBLEM_BASE_URL

__all__ = [
    "ApprovalDefinitionMissingError",
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "CreditLimitExceededError",
    "DuplicateRecordError",
    "DuplicateSkuError",
    "EmployeeTerminatedError",
    "IllegalStateTransitionError",
    "InactiveItemError",
    "InsufficientStockError",
    "LeaveBalanceExceededError",
    "MovementImmutableError",
    "NotFoundError",
    "PayrollEntryImmutableError",
    "PayrollPeriodConflictError",
    "PermissionDeniedError",
    "SelfApprovalForbiddenError",
    "SkyrictError",
    "StartupError",
    "StockReservedError",
    "TenantContextMissingError",
    "TenantDisabledError",
    "TenantMismatchError",
    "TenantNotFoundError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TransferRequiresDistinctWarehousesError",
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
# HR & Payroll domain exceptions (HR-BE-002)
#
# Subclass ConflictError / ValidationError so every new exception inherits a
# sensible generic mapping, and register each below with the exact problem
# type URI from the spec's error table (docs/modules/hr-payroll.md §7).
# ---------------------------------------------------------------------------


class DuplicateRecordError(ConflictError):
    """Duplicate employee number / department name / leave type code."""


class IllegalStateTransitionError(ConflictError):
    """A state-machine guard rejected the mutation (e.g. approve a paid run)."""


class PayrollEntryImmutableError(ConflictError):
    """An entry in an approved/paid run was edited."""


class EmployeeTerminatedError(ConflictError):
    """Activity blocked on a terminated employee (re-hire or post-termination)."""


class PayrollPeriodConflictError(ConflictError):
    """A payroll run overlaps another active run's period."""


class LeaveBalanceExceededError(ValidationError):
    """A negative movement would drive an accrual balance below zero."""


class SelfApprovalForbiddenError(ValidationError):
    """The actor is the requesting employee (no self-approval)."""


# ---------------------------------------------------------------------------
# Inventory domain exceptions (INV-BE-002)
# ---------------------------------------------------------------------------


class InsufficientStockError(ConflictError):
    """The requested mutation would push stock below zero (409)."""

    message = "Insufficient stock for the requested quantity"
    code = "INSUFFICIENT_STOCK"


class DuplicateSkuError(ConflictError):
    """A product with the same SKU already exists in this tenant (409)."""

    message = "A product with this SKU already exists"
    code = "DUPLICATE_SKU"


class MovementImmutableError(ConflictError):
    """The ledger is append-only: a source ref was already applied (409)."""

    message = "Stock movements are immutable and cannot be replayed"
    code = "MOVEMENT_IMMUTABLE"


class StockReservedError(ConflictError):
    """Cannot deactivate an item that still has open reservations (409).

    Mirrors the ERP rule that an item with open commitments cannot be
    archived: reservations are promises to external documents and must be
    released or fulfilled before the item can be deactivated. Plain on-hand
    quantity is NOT blocked - it stays on the books and is written off via a
    stock adjustment on the archived item.
    """

    message = "Cannot deactivate: reserved quantity still exists"
    code = "STOCK_RESERVED"


class InactiveItemError(ConflictError):
    """Cannot post stock against an archived (inactive) item (409).

    Production ERPs apply a "posting block" to deactivated items: new sales,
    transfers and reservations are refused, but write-off adjustments remain
    allowed so remaining on-hand quantity can be zeroed out.
    """

    message = "Cannot post stock against an inactive item"
    code = "ITEM_INACTIVE"


class TransferRequiresDistinctWarehousesError(ValidationError):
    """Transfer source and destination must be different warehouses (422)."""

    message = "Transfer source and destination warehouses must be different"
    code = "TRANSFER_REQUIRES_DISTINCT_WAREHOUSES"


# ---------------------------------------------------------------------------
# CRM & Sales domain exceptions (CRM-BE-002)
# ---------------------------------------------------------------------------


class CreditLimitExceededError(ValidationError):
    """The customer's credit limit would be exceeded by this order (422)."""

    message = "Customer credit limit would be exceeded"
    code = "CREDIT_LIMIT_EXCEEDED"


class AiServiceUnavailableError(SkyrictError):
    """The ai-agent microservice is unreachable or timed out (503).

    Raised ONLY for transport failures while proxying /api/v1/ai/* -
    upstream application errors pass through untouched. The frontend's
    mock-fallback policy consumes the typed 503.
    """

    message = "AI service is temporarily unavailable"
    code = "AI_UNAVAILABLE"


class ApprovalDefinitionMissingError(SkyrictError):
    """A tenant enabled the approval engine but has no active definition (500).

    A controlled configuration error, NOT an authorization bypass: when the
    per-tenant approval flag is ON the engine is mandatory, so a missing
    active workflow definition must fail the submission (the journal entry
    stays pre-posting) instead of silently posting without approval. This is
    a server-side provisioning problem (the tenant flag was turned on before
    an operator seeded the definition); expose the typed problem so ops can
    react, while the payload never reveals internals.
    """

    message = "No active approval definition is configured for this resource"
    code = "APPROVAL_DEFINITION_MISSING"


# Module-private alias of the shared public error contract. An RFC 7807 problem
# `type` is a published identifier that clients branch on, so the base belongs
# in one place in skyrict-common rather than being restated per service. It was
# restated per service, twice over (once here, once in core/constants.py), and
# drifted to a retired domain while the live host moved on - pre-release audit
# finding 16. The alias keeps the ~30 f-strings below short and file-private.
_PROBLEM_BASE = PROBLEM_BASE_URL

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
    # HR & Payroll (docs/modules/hr-payroll.md §7 error table).
    DuplicateRecordError: (409, f"{_PROBLEM_BASE}/duplicate-record"),
    IllegalStateTransitionError: (409, f"{_PROBLEM_BASE}/illegal-state-transition"),
    PayrollEntryImmutableError: (409, f"{_PROBLEM_BASE}/payroll-entry-immutable"),
    EmployeeTerminatedError: (409, f"{_PROBLEM_BASE}/employee-terminated"),
    PayrollPeriodConflictError: (409, f"{_PROBLEM_BASE}/payroll-period-conflict"),
    LeaveBalanceExceededError: (422, f"{_PROBLEM_BASE}/leave-balance-exceeded"),
    SelfApprovalForbiddenError: (422, f"{_PROBLEM_BASE}/self-approval-forbidden"),
    # CRM & Sales (docs/modules/sales-crm.md §7 error table).
    CreditLimitExceededError: (422, f"{_PROBLEM_BASE}/credit-limit-exceeded"),
    # AI proxy transport failures (docs/modules/skyrict-ai/... §6).
    AiServiceUnavailableError: (503, f"{_PROBLEM_BASE}/ai-unavailable"),
    # Approval engine configuration failures (SKY-92): flag ON but no seeded
    # definition - a controlled server-config error, never a silent bypass.
    ApprovalDefinitionMissingError: (500, f"{_PROBLEM_BASE}/approval-definition-missing"),
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


def _json_safe(value: Any) -> Any:
    """Recursively coerce pydantic error payloads into JSON-serializable values.

    Validator-raised errors carry live exception objects in ``ctx`` (e.g.
    ``{"error": ValueError(...)}``) which ``json.dumps`` cannot serialize;
    those are stringified in place.
    """
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


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

    return JSONResponse(status_code=status_code, content=body)


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return FastAPI body-validation failures as RFC 7807 (422)."""
    errors = [_json_safe(error) for error in exc.errors()]
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
    from core.core.logging import get_logger

    logger = get_logger("core.exceptions")
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
