"""HR gateway - read-only access to the core monolith's HR data.

The AI agent owns NO HR tables: the Copilot answers are grounded in core's
existing endpoints, fetched over HTTP with the CALLER's own JWT + tenant slug
(spec §1.4 "AI is a proxy, not a bypass"). The :class:`HrGatewayPort` protocol
is what the engine depends on; tests fake it, production binds
:class:`HttpHrGateway`.

Two data tiers, both enforced by core:
- L1 aggregates (``/ai/hr/overview``, ``/ai/hr/tenure``) and the tenant leave
  policy (``/hr/leave/policy``) - aggregate counts/bands/policy, no per-person
  PII. Available to any ``erp.hr.ai.read`` + ``erp.ai.invoke`` holder.
- Standard employee rows (``/hr/employees``, gated by ``erp.hr.read``) and the
  L2 per-employee AI signals (``/ai/hr/attrition``, gated by the
  ``erp.hr.ai.individual`` owner/exec key). Core returns a 403 to non-holders;
  the gateway detects that 403 and degrades to ``None`` so the engine keeps
  answering from aggregate context rather than leaking or erroring.

Money rule: an ``EmployeeRef`` never carries compensation - pay is sensitive
financial data and the Copilot prompt must not contain amounts. Compensation
stays in core.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

import httpx
import structlog

from ai_agent.core.exceptions import AiUnavailableError

logger = structlog.get_logger("ai_agent.hr_gateway")


@dataclass(frozen=True, slots=True)
class HrOverviewCtx:
    """L1 headcount/tenure overview - aggregate numbers only."""

    total_headcount: int
    departments: tuple[tuple[str, int], ...]
    tenure_bands: tuple[tuple[str, int], ...]
    narrative: str


@dataclass(frozen=True, slots=True)
class HrTenureCtx:
    """L1 tenure-band summary - aggregate narrative only."""

    narrative: str


@dataclass(frozen=True, slots=True)
class HrLeavePolicyCtx:
    """The tenant's leave policy (structured, no PII)."""

    casual_days_per_year: int | None
    sick_days_per_year: int | None
    effective_from: str | None


@dataclass(frozen=True, slots=True)
class HrEmployeeRef:
    """One employee row from the standard ``/hr/employees`` endpoint.

    Identity/job fields only - compensation is deliberately excluded (money
    must not enter the Copilot prompt). Core returns these rows only to
    ``erp.hr.read`` holders; the gateway forwards the caller's scoped identity.
    """

    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    job_title: str
    hire_date: date
    employment_status: str
    email: str | None = None
    phone: str | None = None
    department_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AttritionRiskRef:
    """One per-employee attrition risk row from the L2 ``/ai/hr/attrition`` body.

    Only reachable by ``erp.hr.ai.individual`` holders (owner/exec); core
    short-circuits everyone else. Carries the same detail the admin panel shows
    that role.
    """

    employee_id: UUID
    employee_number: str | None
    name: str | None
    department_name: str | None
    risk_band: str
    score: float
    confidence: float
    factors: tuple[str, ...] = ()


class HrGatewayPort(Protocol):
    """Read-only HR reads, scoped by the forwarded caller's identity."""

    async def get_overview(self) -> HrOverviewCtx | None: ...
    async def get_tenure(self) -> HrTenureCtx | None: ...
    async def get_leave_policy(self) -> HrLeavePolicyCtx | None: ...
    async def list_employees(self) -> list[HrEmployeeRef]: ...
    async def get_attrition(self) -> list[AttritionRiskRef] | None: ...


class HttpHrGateway:
    """One request's gateway: forwards the user's JWT + tenant slug to core."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        tenant_slug: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._tenant_slug = tenant_slug

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._bearer_token}",
            "X-Tenant-Slug": self._tenant_slug,
        }

    def _create_client(self) -> httpx.AsyncClient:
        """Create the per-call HTTP client (overridable seam for tests)."""
        return httpx.AsyncClient(timeout=10.0)

    async def get_overview(self) -> HrOverviewCtx | None:
        payload = await self._get("/api/v1/ai/hr/overview")
        if payload is None:
            return None
        data = _envelope_data(payload)
        return HrOverviewCtx(
            total_headcount=_as_int(data.get("total_headcount"), 0),
            departments=_departments(data),
            tenure_bands=_bands(data.get("tenure_bands")),
            narrative=str(data.get("narrative") or ""),
        )

    async def get_tenure(self) -> HrTenureCtx | None:
        payload = await self._get("/api/v1/ai/hr/tenure")
        if payload is None:
            return None
        data = _envelope_data(payload)
        return HrTenureCtx(narrative=str(data.get("narrative") or ""))

    async def get_leave_policy(self) -> HrLeavePolicyCtx | None:
        payload = await self._get("/api/v1/hr/leave/policy")
        if payload is None:
            return None
        data = _envelope_data(payload)
        return HrLeavePolicyCtx(
            casual_days_per_year=_as_opt_int(data.get("casual_days_per_year")),
            sick_days_per_year=_as_opt_int(data.get("sick_days_per_year")),
            effective_from=(
                None if data.get("effective_from") is None else str(data["effective_from"])
            ),
        )

    async def list_employees(self) -> list[HrEmployeeRef]:
        """Standard employee rows (identity/job only) for ``erp.hr.read`` holders.

        A 403/404 or transport failure degrades to ``[]`` so the engine keeps
        answering from aggregate context. Compensation is never requested here.
        """
        payload = await self._get("/api/v1/hr/employees?limit=100")
        if payload is None:
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        employees: list[HrEmployeeRef] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            employees.append(_parse_employee(item))
        return employees

    async def get_attrition(self) -> list[AttritionRiskRef] | None:
        """L2 per-employee attrition risk, only for ``erp.hr.ai.individual`` holders.

        Core returns a 403 with an L1 aggregates body to non-holders; we detect
        that and return ``None`` so the engine never conflates grant-denied with
        "no risk data". Returns ``[]`` for a healthy tenant with no scored rows.
        """
        payload, status = await self._get_with_status("/api/v1/ai/hr/attrition")
        if status == 403 or payload is None:
            return None
        data = payload.get("data")
        employees_raw = data.get("employees") if isinstance(data, dict) else None
        if not isinstance(employees_raw, list):
            return None
        risks: list[AttritionRiskRef] = []
        for item in employees_raw:
            if not isinstance(item, dict):
                continue
            risks.append(_parse_attrition_risk(item))
        return risks

    async def _get(self, path: str) -> dict[str, object] | None:
        """GET one envelope; non-200 or transport failures degrade to None."""
        payload, status = await self._get_with_status(path)
        return payload if status == 200 else None

    async def _get_with_status(self, path: str) -> tuple[dict[str, object] | None, int]:
        """GET one envelope, returning ``(payload, http_status)``.

        A transport/encode failure still raises :class:`AiUnavailableError` (the
        service is genuinely down); a non-200 HTTP response returns its parsed
        body and status so callers can distinguish grant-denied (403) from other
        outcomes without swallowing outages.
        """
        try:
            async with self._create_client() as client:
                response = await client.get(f"{self._base_url}{path}", headers=self._headers())
        except httpx.HTTPError as exc:
            logger.warning("hr_gateway_unreachable", path=path)
            raise AiUnavailableError("HR service is temporarily unavailable") from exc
        if response.status_code != 200:
            logger.warning("hr_gateway_non_ok", path=path, status=response.status_code)
            return None, response.status_code
        try:
            return _as_json_dict(response.json()), 200
        except ValueError as exc:
            logger.warning("hr_gateway_bad_body", path=path)
            raise AiUnavailableError("HR service returned an unusable response") from exc


def _as_json_dict(value: object) -> dict[str, object]:
    """Validate a JSON body is an object (any other shape is an empty dict)."""
    return value if isinstance(value, dict) else {}


def _envelope_data(payload: dict[str, object]) -> dict[str, object]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _departments(data: dict[str, object]) -> tuple[tuple[str, int], ...]:
    raw = data.get("departments")
    if not isinstance(raw, list):
        return ()
    out: list[tuple[str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("department_name") or "")
        count = _as_int(item.get("count"), 0)
        if name:
            out.append((name, count))
    return tuple(out)


def _bands(raw: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(raw, list):
        return ()
    out: list[tuple[str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append((str(item.get("band") or ""), _as_int(item.get("count"), 0)))
    return tuple(out)


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_opt_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_employee(item: dict[str, object]) -> HrEmployeeRef:
    hire = item.get("hire_date")
    return HrEmployeeRef(
        id=_as_uuid(item["id"]),
        employee_number=str(item["employee_number"]),
        first_name=str(item["first_name"]),
        last_name=str(item["last_name"]),
        job_title=str(item["job_title"]),
        hire_date=(date.fromisoformat(str(hire)) if hire is not None else date.min),
        employment_status=str(item["employment_status"]),
        email=None if item.get("email") is None else str(item["email"]),
        phone=None if item.get("phone") is None else str(item["phone"]),
        department_id=_as_opt_uuid(item.get("department_id")),
    )


def _parse_attrition_risk(item: dict[str, object]) -> AttritionRiskRef:
    factors_raw = item.get("factors")
    factors: tuple[str, ...] = ()
    if isinstance(factors_raw, list):
        parts: list[str] = []
        for factor in factors_raw:
            if not isinstance(factor, dict):
                continue
            label = factor.get("label") or factor.get("factor")
            if label:
                parts.append(str(label))
        factors = tuple(parts)
    return AttritionRiskRef(
        employee_id=_as_uuid(item["employee_id"]),
        employee_number=None
        if item.get("employee_number") is None
        else str(item["employee_number"]),
        name=None if item.get("name") is None else str(item["name"]),
        department_name=(
            None if item.get("department_name") is None else str(item["department_name"])
        ),
        risk_band=str(item["risk_band"]),
        score=float(str(item["score"])),
        confidence=float(str(item["confidence"])),
        factors=factors,
    )


def _as_uuid(value: object) -> UUID:
    return UUID(str(value))


def _as_opt_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    return UUID(str(value))
