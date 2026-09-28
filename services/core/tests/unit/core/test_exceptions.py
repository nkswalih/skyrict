"""Exception-to-status mapping tests - the RFC 7807 tenant error contract.

Tenant error mapping (ERP-FND-001):
  missing tenant context -> 400 tenant-context-missing
  token/routed tenant mismatch -> 401 tenant-mismatch
  unknown tenant slug -> 404 tenant-not-found
  disabled tenant -> 403 tenant-disabled
"""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from core.core import exceptions as core_exceptions
from core.core.exceptions import (
    AiServiceUnavailableError,
    CreditLimitExceededError,
    DuplicateRecordError,
    DuplicateSkuError,
    InsufficientStockError,
    MovementImmutableError,
    TransferRequiresDistinctWarehousesError,
    _status_and_type,
    unhandled_error_handler,
)
from skyrict_common.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    SkyrictError,
    TenantContextMissingError,
    TenantDisabledError,
    TenantMismatchError,
    TenantNotFoundError,
    ValidationError,
)
from skyrict_common.problems import PROBLEM_BASE_URL


class TestTenantErrorMapping:
    def test_missing_context_is_400(self) -> None:
        status, problem_type = _status_and_type(TenantContextMissingError("missing"))
        assert status == 400
        assert problem_type.endswith("/tenant-context-missing")

    def test_mismatch_is_401(self) -> None:
        status, problem_type = _status_and_type(TenantMismatchError("mismatch"))
        assert status == 401
        assert problem_type.endswith("/tenant-mismatch")

    def test_unknown_tenant_is_404(self) -> None:
        status, problem_type = _status_and_type(TenantNotFoundError("unknown"))
        assert status == 404
        assert problem_type.endswith("/tenant-not-found")

    def test_disabled_tenant_is_403(self) -> None:
        status, problem_type = _status_and_type(TenantDisabledError("disabled"))
        assert status == 403
        assert problem_type.endswith("/tenant-disabled")

    def test_missing_permission_is_403_permission_denied(self) -> None:
        status, problem_type = _status_and_type(PermissionDeniedError("no grant"))
        assert status == 403
        assert problem_type.endswith("/permission-denied")


class TestConflictMapping:
    """INV-BE-002: ledger conflicts surface as RFC 7807 409 (not a 500)."""

    def test_conflict_base_maps_to_409(self) -> None:
        status, problem_type = _status_and_type(ConflictError("boom"))
        assert status == 409
        assert problem_type.endswith("/conflict")

    def test_insufficient_stock_is_409(self) -> None:
        status, problem_type = _status_and_type(InsufficientStockError())
        assert status == 409
        assert problem_type.endswith("/conflict")
        assert InsufficientStockError().code == "INSUFFICIENT_STOCK"

    def test_duplicate_sku_is_409(self) -> None:
        status, problem_type = _status_and_type(DuplicateSkuError())
        assert status == 409
        assert problem_type.endswith("/conflict")
        assert DuplicateSkuError().code == "DUPLICATE_SKU"

    def test_movement_immutable_is_409(self) -> None:
        status, problem_type = _status_and_type(MovementImmutableError())
        assert status == 409
        assert problem_type.endswith("/conflict")
        assert MovementImmutableError().code == "MOVEMENT_IMMUTABLE"


class TestValidationMapping:
    def test_validation_base_maps_to_422(self) -> None:
        status, problem_type = _status_and_type(ValidationError("bad"))
        assert status == 422
        assert problem_type.endswith("/validation-error")

    def test_transfer_same_warehouse_is_422(self) -> None:
        status, problem_type = _status_and_type(TransferRequiresDistinctWarehousesError())
        assert status == 422
        assert problem_type.endswith("/validation-error")
        assert (
            TransferRequiresDistinctWarehousesError().code
            == "TRANSFER_REQUIRES_DISTINCT_WAREHOUSES"
        )


# ---------------------------------------------------------------------------
# SKY-97: error-contract sweep - every documented exception resolves to a
# structured 4xx/5xx (never an unmapped 500) and problem types stay on the
# RFC 7807 base URL. The MRO walk in _status_and_type is the single source
# of truth for what a client sees; these tests pin its enumerable surface so
# a newly added exception can never silently fall through to a 500.
# ---------------------------------------------------------------------------

ALL_SKYRICT_SUBCLASSES = sorted(
    (
        obj
        for _, obj in inspect.getmembers(core_exceptions, inspect.isclass)
        if obj is not SkyrictError and issubclass(obj, SkyrictError)
    ),
    key=lambda cls: cls.__name__,
)


@pytest.mark.parametrize(
    "exc_cls",
    list(core_exceptions._STATUS_MAP),
    ids=lambda cls: cls.__name__,
)
def test_every_mapped_exception_resolves_to_its_declared_tuple(exc_cls) -> None:
    """Each _STATUS_MAP entry must round-trip through the MRO resolver."""
    status, problem_type = _status_and_type(exc_cls())
    assert (status, problem_type) == core_exceptions._STATUS_MAP[exc_cls]


@pytest.mark.parametrize(
    "exc_cls",
    ALL_SKYRICT_SUBCLASSES,
    ids=lambda cls: cls.__name__,
)
def test_no_skyrict_subclass_falls_through_to_generic_internal_error(exc_cls) -> None:
    """Every documented exception resolves via its MRO to a defined problem type.

    Resolution to the (500, /internal-error) default means the exception was
    added without a _STATUS_MAP entry OR without inheriting from a mapped base
    class - the exact silent-500 failure mode SKY-97 is eradicating. Deliberate
    server-config faults (e.g. ApprovalDefinitionMissingError) may legitimately
    map to 500, but only when they carry a specific problem type.
    """
    _status, problem_type = _status_and_type(exc_cls())
    assert problem_type != f"{core_exceptions._PROBLEM_BASE}/internal-error", (
        f"{exc_cls.__name__} unmapped - resolves to generic internal-error"
    )
    assert problem_type.startswith(f"{PROBLEM_BASE_URL}/")


@pytest.mark.parametrize(
    "exc_cls",
    [
        ConflictError,
        ValidationError,
        NotFoundError,
        AuthorizationError,
        PermissionDeniedError,
        TenantContextMissingError,
        TenantDisabledError,
        DuplicateRecordError,
        DuplicateSkuError,
        InsufficientStockError,
        MovementImmutableError,
        CreditLimitExceededError,
        TransferRequiresDistinctWarehousesError,
    ],
    ids=lambda cls: cls.__name__,
)
def test_client_errors_resolve_to_4xx(exc_cls) -> None:
    """Business-rule violations must never surface as 5xx."""
    status, _ = _status_and_type(exc_cls())
    assert 400 <= status < 500, f"{exc_cls.__name__} mapped to {status} (should be 4xx)"


def test_ai_service_fault_is_explicitly_503() -> None:
    """Provider/upstream faults map to 503 ai-unavailable, not a bare 500."""
    status, problem_type = _status_and_type(AiServiceUnavailableError())
    assert status == 503
    assert problem_type == f"{PROBLEM_BASE_URL}/ai-unavailable"


async def test_unhandled_error_response_never_leaks_internals() -> None:
    """The 500 catch-all must sanitize: no traceback, no PII, stable shape."""
    request = SimpleNamespace(
        state=SimpleNamespace(request_id="req-sweep-1"),
        url=SimpleNamespace(path="/api/v1/hr/departments"),
        method="POST",
    )
    response = await unhandled_error_handler(request, RuntimeError("secret internal detail"))
    body = json.loads(response.body)
    raw = response.body.decode()

    assert response.status_code == 500
    assert body["type"] == f"{PROBLEM_BASE_URL}/internal-error"
    assert body["detail"] == "An unexpected error occurred. Please try again later."
    assert body["instance"] == "req-sweep-1"
    assert "secret internal detail" not in raw
    assert "Traceback" not in raw
    assert "RuntimeError" not in raw
