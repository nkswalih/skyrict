"""SKY-97: RFC 7807 error-contract sweep for the ai-agent service.

Pins the same invariants as core/identity: every documented SkyrictError
resolves via the MRO walk to a defined problem type (never the generic
/internal-error fallback), all client-facing errors resolve 4xx, the SKY-57
AI error contract carries stable statuses/types, and the 500 catch-all
leaks nothing internal.
"""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from ai_agent.core import exceptions as ai_exceptions
from ai_agent.core.exceptions import (
    AiDataResidencyError,
    AiInvalidResponseError,
    AiRateLimitError,
    AiUnavailableError,
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
    ValidationError,
)
from skyrict_common.problems import PROBLEM_BASE_URL

ALL_SKYRICT_SUBCLASSES = sorted(
    (
        obj
        for _, obj in inspect.getmembers(ai_exceptions, inspect.isclass)
        if obj is not SkyrictError and issubclass(obj, SkyrictError)
    ),
    key=lambda cls: cls.__name__,
)


@pytest.mark.parametrize(
    "exc_cls",
    list(ai_exceptions._STATUS_MAP),
    ids=lambda cls: cls.__name__,
)
def test_every_mapped_exception_resolves_to_its_declared_tuple(exc_cls) -> None:
    """Each _STATUS_MAP entry must round-trip through the MRO resolver."""
    status, problem_type = _status_and_type(exc_cls())
    assert (status, problem_type) == ai_exceptions._STATUS_MAP[exc_cls]


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
    assert problem_type != f"{ai_exceptions._PROBLEM_BASE}/internal-error", (
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
    ],
    ids=lambda cls: cls.__name__,
)
def test_client_errors_resolve_to_4xx(exc_cls) -> None:
    """Business-rule violations must never surface as 5xx."""
    status, _ = _status_and_type(exc_cls())
    assert 400 <= status < 500, f"{exc_cls.__name__} mapped to {status} (should be 4xx)"


@pytest.mark.parametrize(
    ("exc_cls", "expected_status", "expected_type"),
    [
        pytest.param(AiUnavailableError, 503, "ai-unavailable", id="AiUnavailableError"),
        pytest.param(
            AiInvalidResponseError, 502, "ai-invalid-response", id="AiInvalidResponseError"
        ),
        pytest.param(AiRateLimitError, 429, "ai-rate-limited", id="AiRateLimitError"),
        pytest.param(AiDataResidencyError, 422, "ai-data-residency", id="AiDataResidencyError"),
    ],
)
def test_ai_error_contract_is_stable(exc_cls, expected_status: int, expected_type: str) -> None:
    """SKY-57: the AI failure contract must not drift from its documented types."""
    status, problem_type = _status_and_type(exc_cls())
    assert status == expected_status
    assert problem_type == f"{PROBLEM_BASE_URL}/{expected_type}"


@pytest.mark.parametrize(
    ("exc_cls", "expected_title"),
    [
        pytest.param(AiUnavailableError, "AiUnavailableError", id="AiUnavailableError"),
        pytest.param(AiRateLimitError, "AiRateLimitError", id="AiRateLimitError"),
    ],
)
async def test_ai_error_body_never_mentions_provider(exc_cls, expected_title: str) -> None:
    """Failure MODE is named, never provider names or internals."""
    request = SimpleNamespace(
        state=SimpleNamespace(request_id="req-ai-1"),
        url=SimpleNamespace(path="/api/v1/ai/chat"),
        method="POST",
    )
    response = await ai_exceptions.skyrict_error_handler(request, exc_cls())
    body = json.loads(response.body)
    assert body["title"] == expected_title
    assert "provider" not in body["detail"].lower()


async def test_ai_unavailable_surfaces_as_separate_url() -> None:
    """A provider fault must not be caught by the generic internal-error path."""
    request = SimpleNamespace(
        state=SimpleNamespace(request_id="req-ai-2"),
        url=SimpleNamespace(path="/api/v1/ai/chat"),
        method="POST",
    )
    response = await ai_exceptions.skyrict_error_handler(request, AiUnavailableError())
    body = json.loads(response.body)
    assert body["status"] == 503
    assert body["type"] == f"{PROBLEM_BASE_URL}/ai-unavailable"
    assert body["instance"] == "req-ai-2"


async def test_unhandled_error_response_never_leaks_internals() -> None:
    """The 500 catch-all must sanitize: no traceback, no PII, stable shape."""
    request = SimpleNamespace(
        state=SimpleNamespace(request_id="req-ai-3"),
        url=SimpleNamespace(path="/api/v1/ai/chat"),
        method="POST",
    )
    response = await unhandled_error_handler(request, RuntimeError("secret internal detail"))
    body = json.loads(response.body)
    raw = response.body.decode()

    assert response.status_code == 500
    assert body["type"] == f"{PROBLEM_BASE_URL}/internal-error"
    assert body["detail"] == "An unexpected error occurred. Please try again later."
    assert body["instance"] == "req-ai-3"
    assert "secret internal detail" not in raw
    assert "Traceback" not in raw
    assert "RuntimeError" not in raw
