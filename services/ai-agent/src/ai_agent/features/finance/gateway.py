"""Finance gateway - read-only access to the core monolith's finance data.

The AI agent owns NO finance tables: every answer is grounded in core's
existing ``/api/v1/finance`` endpoints, fetched with the CALLER's own JWT +
tenant slug (spec §1.4 "AI is a proxy, not a bypass"). The
:class:`FinanceGatewayPort` protocol is what the delegator depends on; tests
fake it, production binds :class:`HttpFinanceGateway`.

Permission/tenant enforcement is core's: every read requires ``erp.finance.read``
and is tenant-scoped by the caller's identity. The gateway forwards that
identity unchanged, so the AI sees exactly the invoices/P&L/AR data the acting
user can already view in the finance UI - never another tenant's data, never a
privileged view.

Money is Decimal throughout (never float); core serializes Decimal fields as
exact strings, which we parse back to Decimal here so prompt rendering shows
exact figures.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

import httpx
import structlog

from ai_agent.core.exceptions import AiUnavailableError

logger = structlog.get_logger("ai_agent.finance_gateway")

# Catalog fetches page through core with this guard so a pathological tenant
# cannot make one finance read loop forever. 20 pages x 100 rows = 2000 rows.
_MAX_CATALOG_PAGES = 20
_CATALOG_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class AccountRef:
    """One chart-of-accounts row (needed to label report lines)."""

    id: uuid.UUID
    code: str
    name: str
    account_type: str


@dataclass(frozen=True, slots=True)
class InvoiceRef:
    """One invoice row - enough to answer status/amount/due questions."""

    id: uuid.UUID
    invoice_number: str
    customer_name: str | None
    status: str
    total: Decimal
    invoice_date: date
    due_date: date
    issued_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PnlRef:
    """Profit & Loss summary for a period."""

    from_date: date
    to_date: date
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


@dataclass(frozen=True, slots=True)
class ArAgingBucketRef:
    """One AR-aging bucket (e.g. current, 1-30, >90)."""

    bucket: str
    count: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ArAgingRef:
    """Accounts receivable aging summary."""

    as_of: date
    total_ar: Decimal
    buckets: tuple[ArAgingBucketRef, ...]


@dataclass(frozen=True, slots=True)
class TrialBalanceRowRef:
    """One trial-balance line (an account's debit/credit side)."""

    code: str
    name: str
    account_type: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True, slots=True)
class TrialBalanceRef:
    """Trial balance as of a date: balanced or not, with its rows."""

    as_of: date
    rows: tuple[TrialBalanceRowRef, ...]
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True, slots=True)
class CashflowPositionRef:
    """One projected month a cash-out date line (opening->closing)."""

    month: str
    opening: Decimal
    inflows: Decimal
    outflows: Decimal
    closing: Decimal


@dataclass(frozen=True, slots=True)
class CashflowProjectionRef:
    """Forward cash-flow projection seeded as of a date."""

    positions: tuple[CashflowPositionRef, ...]


class FinanceGatewayPort(Protocol):
    """Read-only finance queries, scoped by the forwarded caller's identity."""

    async def list_accounts(self) -> list[AccountRef]: ...
    async def list_invoices(self) -> list[InvoiceRef]: ...
    async def get_pnl(self) -> PnlRef | None: ...
    async def get_ar_aging(self) -> ArAgingRef | None: ...
    async def get_trial_balance(self, *, as_of: date) -> TrialBalanceRef | None: ...
    async def get_cashflow_projection(self, *, as_of: date) -> CashflowProjectionRef | None: ...


class HttpFinanceGateway:
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
            # Core resolves tenants via subdomain in prod, X-Tenant-Slug in
            # dev/test; forwarding the slug keeps behavior identical either way.
            "X-Tenant-Slug": self._tenant_slug,
        }

    async def list_accounts(self) -> list[AccountRef]:
        items: list[AccountRef] = []
        payload = await self._get_single("/api/v1/finance/accounts")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []
        for item in data:
            if not isinstance(item, dict):
                continue
            items.append(
                AccountRef(
                    id=_as_uuid(item["id"]),
                    code=str(item["code"]),
                    name=str(item["name"]),
                    account_type=str(item["account_type"]),
                )
            )
        return items

    async def list_invoices(self) -> list[InvoiceRef]:
        # Core's /invoices paginates by offset/limit; stop once a page returns
        # fewer rows than requested (or we hit the hard catalog cap). We do not
        # trust meta.total_pages for termination — core computes it from the
        # current page's row count, not the total.
        items: list[InvoiceRef] = []
        offset = 0
        for _ in range(_MAX_CATALOG_PAGES):
            page_data = await self._get_list(
                "/api/v1/finance/invoices", offset=offset, limit=_CATALOG_PAGE_SIZE
            )
            items.extend(_parse_invoice(item) for item in page_data.items)
            if len(page_data.items) < _CATALOG_PAGE_SIZE:
                break
            offset += _CATALOG_PAGE_SIZE
        return items

    async def get_pnl(self) -> PnlRef | None:
        payload = await self._get_optional("/api/v1/finance/reports/profit-and-loss")
        if payload is None:
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        return PnlRef(
            from_date=_as_date(data["from_date"]),
            to_date=_as_date(data["to_date"]),
            total_revenue=_as_decimal(data["total_revenue"]),
            total_expenses=_as_decimal(data["total_expenses"]),
            net_income=_as_decimal(data["net_income"]),
        )

    async def get_ar_aging(self) -> ArAgingRef | None:
        payload = await self._get_optional("/api/v1/finance/reports/ar-aging")
        if payload is None:
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        buckets_raw = data.get("buckets")
        buckets: list[ArAgingBucketRef] = []
        if isinstance(buckets_raw, list):
            for bucket in buckets_raw:
                if not isinstance(bucket, dict):
                    continue
                buckets.append(
                    ArAgingBucketRef(
                        bucket=str(bucket.get("bucket") or ""),
                        count=int(bucket.get("count") or 0),
                        amount=_as_decimal(bucket.get("amount")),
                    )
                )
        return ArAgingRef(
            as_of=_as_date(data["as_of"]),
            total_ar=_as_decimal(data["total_ar"]),
            buckets=tuple(buckets),
        )

    async def get_trial_balance(self, *, as_of: date) -> TrialBalanceRef | None:
        payload = await self._get_optional(
            "/api/v1/finance/reports/trial-balance", params={"as_of": as_of.isoformat()}
        )
        if payload is None:
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        rows_raw = data.get("rows")
        rows: list[TrialBalanceRowRef] = []
        if isinstance(rows_raw, list):
            for row in rows_raw:
                if not isinstance(row, dict):
                    continue
                rows.append(
                    TrialBalanceRowRef(
                        code=str(row.get("code") or ""),
                        name=str(row.get("name") or ""),
                        account_type=str(row.get("account_type") or ""),
                        debit=_as_decimal(row.get("debit") or 0),
                        credit=_as_decimal(row.get("credit") or 0),
                    )
                )
        return TrialBalanceRef(
            as_of=_as_date(data["as_of"]),
            rows=tuple(rows),
            total_debit=_as_decimal(data["total_debit"]),
            total_credit=_as_decimal(data["total_credit"]),
        )

    async def get_cashflow_projection(self, *, as_of: date) -> CashflowProjectionRef | None:
        payload = await self._get_optional(
            "/api/v1/finance/automation/cashflow-projection", params={"as_of": as_of.isoformat()}
        )
        if payload is None:
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        positions_raw = data.get("positions")
        positions: list[CashflowPositionRef] = []
        if isinstance(positions_raw, list):
            for position in positions_raw:
                if not isinstance(position, dict):
                    continue
                positions.append(
                    CashflowPositionRef(
                        month=str(position.get("month") or ""),
                        opening=_as_decimal(position.get("opening") or 0),
                        inflows=_as_decimal(position.get("inflows") or 0),
                        outflows=_as_decimal(position.get("outflows") or 0),
                        closing=_as_decimal(position.get("closing") or 0),
                    )
                )
        return CashflowProjectionRef(positions=tuple(positions))

    def _create_client(self) -> httpx.AsyncClient:
        """Create the per-call HTTP client (overridable seam for tests)."""
        return httpx.AsyncClient(timeout=10.0)

    async def _get_list(self, path: str, *, offset: int, limit: int) -> _ListPage:
        """GET one ListResponse page; any failure is a typed 503 for the caller."""
        params: dict[str, str] = {"offset": str(offset), "limit": str(limit)}
        try:
            async with self._create_client() as client:
                response = await client.get(
                    f"{self._base_url}{path}", params=params, headers=self._headers()
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("finance_gateway_unreachable", path=path)
            raise AiUnavailableError("Finance service is temporarily unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("finance_gateway_bad_body", path=path)
            raise AiUnavailableError("Finance service returned an unusable response") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise AiUnavailableError("Finance service returned an unusable response")
        if not isinstance(payload.get("meta"), dict):
            raise AiUnavailableError("Finance service returned an unusable response")
        return _ListPage(items=payload["data"])

    async def _get_single(self, path: str) -> dict[str, object]:
        """GET a single-envelope read; failures raise a typed 503."""
        try:
            async with self._create_client() as client:
                response = await client.get(f"{self._base_url}{path}", headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("finance_gateway_unreachable", path=path)
            raise AiUnavailableError("Finance service is temporarily unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("finance_gateway_bad_body", path=path)
            raise AiUnavailableError("Finance service returned an unusable response") from exc
        if not isinstance(payload, dict):
            raise AiUnavailableError("Finance service returned an unusable response")
        return payload

    async def _get_optional(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> dict[str, object] | None:
        """Single-envelope read that degrades to ``None`` on any non-200."""
        try:
            async with self._create_client() as client:
                response = await client.get(
                    f"{self._base_url}{path}", params=params, headers=self._headers()
                )
                if response.status_code != 200:
                    logger.warning("finance_gateway_non_ok", path=path, status=response.status_code)
                    return None
        except httpx.HTTPError as exc:
            logger.warning("finance_gateway_unreachable", path=path)
            raise AiUnavailableError("Finance service is temporarily unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("finance_gateway_bad_body", path=path)
            raise AiUnavailableError("Finance service returned an unusable response") from exc
        return payload if isinstance(payload, dict) else None


@dataclass(frozen=True, slots=True)
class _ListPage:
    """One validated ListResponse page: raw items to parse."""

    items: list[dict[str, object]]


def _parse_invoice(item: dict[str, object]) -> InvoiceRef:
    return InvoiceRef(
        id=_as_uuid(item["id"]),
        invoice_number=str(item["invoice_number"]),
        customer_name=None if item.get("customer_name") is None else str(item["customer_name"]),
        status=str(item["status"]),
        total=_as_decimal(item["total"]),
        invoice_date=_as_date(item["invoice_date"]),
        due_date=_as_date(item["due_date"]),
        issued_at=_as_opt_datetime(item.get("issued_at")),
    )


def _as_uuid(value: object) -> uuid.UUID:
    return uuid.UUID(str(value))


def _as_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _as_date(value: object) -> date:
    return date.fromisoformat(str(value).split("T")[0])


def _as_opt_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
