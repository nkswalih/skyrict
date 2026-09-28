"""Unit tests for the RFC 7807 exception handlers in identity/core/exceptions.py.

Uses a dedicated FastAPI app (built via create_app) with throwaway routes so the
module-level identity.main app is never mutated. Verifies:
  - 404 / 403 / 409 / 422 return RFC 7807 problem+json bodies
  - route-level 404s return the same shape (StarletteHTTPException handler)
  - unhandled exceptions return a sanitized 500 with no stack-trace leak
  - every SkyrictError subclass maps to the correct status (MRO walking)
  - the RFC 7807 ``instance`` field equals the X-Request-ID tracing value
"""

from __future__ import annotations

import inspect
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import APIRouter, FastAPI

import identity.api.middleware as middleware_module
from identity.core import exceptions as identity_exceptions
from identity.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    _status_and_type,
)
from identity.main import create_app
from skyrict_common.exceptions import (
    MFAVerificationError,
    SessionNotFoundError,
    SkyrictError,
)
from skyrict_common.problems import PROBLEM_BASE_URL


class TeamNotFoundError(NotFoundError):
    """Not in the status map on purpose - must resolve via MRO to NotFoundError."""

    message = "Team not found"
    code = "TEAM_NOT_FOUND"


@pytest.fixture
def test_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # Handler tests exercise RFC 7807 mapping, not tenant resolution. Stub the
    # middleware's tenant lookup (TenantRepository.get_by_slug) so these tests
    # run without a database. The fake model must expose every field the
    # repository's ORM->entity mapper reads.
    now = datetime.now(UTC)
    fake_tenant = SimpleNamespace(
        id=uuid.uuid4(),
        name="Default Org",
        slug="default",
        is_active=True,
        plan_tier="free",
        industry=None,
        billing_address=None,
        onboarding_completed_at=None,
        trial_ends_at=None,
        subscription_status="none",
        stripe_customer_id=None,
        stripe_subscription_id=None,
        billing_email=None,
        grace_started_at=None,
        created_at=now,
        updated_at=now,
    )

    class _FakeResult:
        def __init__(self, tenant: object) -> None:
            self._tenant = tenant

        def scalar_one_or_none(self) -> object:
            return self._tenant

    class _FakeSession:
        async def execute(self, stmt: object) -> _FakeResult:
            return _FakeResult(fake_tenant)

    @asynccontextmanager
    async def _noop_db_session():
        yield _FakeSession()

    monkeypatch.setattr(middleware_module, "async_session_factory", _noop_db_session)

    router = APIRouter(prefix="/test")

    @router.get("/boom/not-found")
    async def not_found() -> None:
        raise NotFoundError("User does not exist")

    @router.get("/boom/team-not-found")
    async def team_not_found() -> None:
        raise TeamNotFoundError()

    @router.get("/boom/forbidden")
    async def forbidden() -> None:
        raise PermissionDeniedError()

    @router.get("/boom/conflict")
    async def conflict() -> None:
        raise ConflictError("A user with this email already exists")

    @router.get("/boom/session-not-found")
    async def session_not_found() -> None:
        raise SessionNotFoundError()

    @router.get("/boom/mfa-verification")
    async def mfa_verification() -> None:
        raise MFAVerificationError()

    @router.get("/boom/unhandled")
    async def unhandled() -> None:
        raise RuntimeError("secret internal detail -- connection refused")

    @router.post("/boom/echo")
    async def echo(payload: dict[str, str]) -> dict[str, str]:
        return payload

    application = create_app()
    application.include_router(router)
    return application


@pytest.fixture
async def http_client(test_app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    # In the test environment the middleware resolves tenants from X-Tenant-Slug;
    # the lookup is stubbed by the test_app fixture.
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Tenant-Slug": "default"}
    ) as client:
        yield client


def _assert_rfc7807_shape(body: dict, status: int, problem_type: str, detail: str) -> None:
    """Assert the response body follows the RFC 7807 problem+json contract."""
    assert body["type"] == problem_type
    assert body["status"] == status
    assert "title" in body
    assert body["detail"] == detail
    assert isinstance(body["instance"], str)
    assert body["instance"]


async def test_not_found_returns_rfc7807(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/test/boom/not-found")
    assert response.status_code == 404
    _assert_rfc7807_shape(
        response.json(),
        404,
        f"{PROBLEM_BASE_URL}/not-found",
        "User does not exist",
    )
    assert response.json()["title"] == "NotFoundError"


async def test_unmapped_subclass_maps_via_mro(http_client: httpx.AsyncClient) -> None:
    """A NotFoundError subclass absent from the map still resolves to 404."""
    response = await http_client.get("/test/boom/team-not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["type"] == f"{PROBLEM_BASE_URL}/not-found"
    assert body["title"] == "TeamNotFoundError"


async def test_permission_denied_returns_403(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/test/boom/forbidden")
    assert response.status_code == 403
    _assert_rfc7807_shape(
        response.json(),
        403,
        f"{PROBLEM_BASE_URL}/permission-denied",
        "You do not have permission to access this resource",
    )


async def test_conflict_returns_409(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/test/boom/conflict")
    assert response.status_code == 409
    _assert_rfc7807_shape(
        response.json(),
        409,
        f"{PROBLEM_BASE_URL}/conflict",
        "A user with this email already exists",
    )


async def test_session_not_found_returns_404(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/test/boom/session-not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["type"] == f"{PROBLEM_BASE_URL}/session-not-found"


async def test_mfa_verification_returns_403(http_client: httpx.AsyncClient) -> None:
    """Previously unmapped subclasses must not fall through to 500."""
    response = await http_client.get("/test/boom/mfa-verification")
    assert response.status_code == 403
    body = response.json()
    assert body["type"] == f"{PROBLEM_BASE_URL}/mfa-verification-error"


async def test_request_validation_error_returns_422(http_client: httpx.AsyncClient) -> None:
    response = await http_client.post("/test/boom/echo", json={"email": 123})
    assert response.status_code == 422
    body = response.json()
    _assert_rfc7807_shape(
        body,
        422,
        f"{PROBLEM_BASE_URL}/validation-error",
        body["detail"],
    )
    assert body["title"] == "Validation Error"
    assert isinstance(body["errors"], list)
    assert body["errors"]


async def test_route_not_found_returns_rfc7807(http_client: httpx.AsyncClient) -> None:
    """A URL that matches no route still returns the RFC 7807 contract."""
    response = await http_client.get("/test/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["type"] == f"{PROBLEM_BASE_URL}/http-404"
    assert body["status"] == 404
    assert isinstance(body["instance"], str)


async def test_unhandled_exception_returns_sanitized_500(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/test/boom/unhandled")
    assert response.status_code == 500
    body = response.json()
    assert body["type"] == f"{PROBLEM_BASE_URL}/internal-error"
    assert body["title"] == "Internal Server Error"
    assert body["detail"] == "An unexpected error occurred. Please try again later."

    raw = response.text
    assert "secret internal detail" not in raw
    assert "Traceback" not in raw
    assert "RuntimeError" not in raw
    assert isinstance(body["instance"], str)


async def test_instance_equals_request_id(http_client: httpx.AsyncClient) -> None:
    """The RFC 7807 ``instance`` field must match the X-Request-ID trace value."""
    response = await http_client.get("/test/boom/not-found")
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert response.json()["instance"] == request_id


# ---------------------------------------------------------------------------
# SKY-97: RFC 7807 error-contract sweep
#
# Same parametrized invariants as core/identity - pins the MRO walk so a newly
# added exception can never silently fall through to the generic 500.
# ---------------------------------------------------------------------------

ALL_SKYRICT_SUBCLASSES = sorted(
    (
        obj
        for _, obj in inspect.getmembers(identity_exceptions, inspect.isclass)
        if obj is not SkyrictError and issubclass(obj, SkyrictError)
    ),
    key=lambda cls: cls.__name__,
)


@pytest.mark.parametrize(
    "exc_cls",
    list(identity_exceptions._STATUS_MAP),
    ids=lambda cls: cls.__name__,
)
def test_every_mapped_exception_resolves_to_its_declared_tuple(exc_cls) -> None:
    """Each _STATUS_MAP entry must round-trip through the MRO resolver."""
    status, problem_type = _status_and_type(exc_cls())
    assert (status, problem_type) == identity_exceptions._STATUS_MAP[exc_cls]


@pytest.mark.parametrize(
    "exc_cls",
    ALL_SKYRICT_SUBCLASSES,
    ids=lambda cls: cls.__name__,
)
def test_no_skyrict_subclass_falls_through_to_generic_internal_error(exc_cls) -> None:
    """Every documented exception resolves via its MRO to a defined problem type.

    Resolution to the (500, /internal-error) default means the exception was
    added without a _STATUS_MAP entry OR without inheriting from a mapped base
    class - the exact silent-500 failure mode SKY-97 is eradicating.
    """
    _, problem_type = _status_and_type(exc_cls())
    assert problem_type != f"{identity_exceptions._PROBLEM_BASE}/internal-error", (
        f"{exc_cls.__name__} unmapped - resolves to generic internal-error"
    )
    assert problem_type.startswith(f"{PROBLEM_BASE_URL}/")


@pytest.mark.parametrize(
    "exc_cls",
    [
        ConflictError,
        PermissionDeniedError,
        NotFoundError,
        MFAVerificationError,
        SessionNotFoundError,
    ],
    ids=lambda cls: cls.__name__,
)
def test_client_errors_resolve_to_4xx(exc_cls) -> None:
    """Business-rule violations must never surface as 5xx."""
    status, _ = _status_and_type(exc_cls())
    assert 400 <= status < 500, f"{exc_cls.__name__} mapped to {status} (should be 4xx)"
