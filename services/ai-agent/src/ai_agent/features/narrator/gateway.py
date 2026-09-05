"""Core gateway - read-only access to the four ERP modules over HTTP.

The narrator owns no ERP tables: every signal is computed from core's existing
HTTP API (SKY-63; same "AI is a proxy, not a bypass" rule as nl_query). The
:class:`CoreGatewayPort` protocol is what engines depend on; tests fake it,
production binds :class:`HttpCoreGateway`.

Adapter notes (verified against core's routers):
- module prefixes under ``/api/v1``: finance ``/finance``, sales
  ``/sales/orders``, inventory ``/inventory``, crm ``/crm``;
- responses use the shared envelope ``{"success": ..., "data": ..., "meta": ...}``;
- money arrives either as a number or as ``[amount, currency]`` tuples -
  normalized to ``Decimal`` HERE so engines never see wire formats;
- list endpoints paginate; fetches are page-capped to bound one digest run.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol

import httpx
import structlog

from ai_agent.core.config import settings
from ai_agent.core.exceptions import AiUnavailableError

logger = structlog.get_logger("ai_agent.narrator_gateway")

_MAX_CATALOG_PAGES = 20
_CATALOG_PAGE_SIZE = 100
_RECENT_WIN_DAYS = 30

_CASH_CODES = frozenset({"1100", "1200"})


@dataclass(frozen=True, slots=True)
class FinanceSignals:
    cash_balance: Decimal
    total_ar: Decimal
    ar_buckets: dict[str, Decimal]
    payables: Decimal
    net_income: Decimal


@dataclass(frozen=True, slots=True)
class SalesSignals:
    confirmed_unfulfilled_value: Decimal


@dataclass(frozen=True, slots=True)
class InventorySignals:
    stock_out_count: int
    low_stock_count: int
    total_sku_count: int


@dataclass(frozen=True, slots=True)
class StockHealthSignals:
    """Dead-stock / slow-mover health read from core's health summary.

    ``tied_up_capital`` is 0 when the caller lacks ``erp.inventory.cost``
    (core blanks the figure server-side); engines present it as advisory.
    """

    dead_stock_count: int
    slow_mover_count: int
    tied_up_capital: Decimal


@dataclass(frozen=True, slots=True)
class CrmSignals:
    open_opportunities: int
    won_recent_days: int
    win_rate: Decimal


class CoreGatewayPort(Protocol):
    """Read-only cross-module queries, scoped by the caller's identity."""

    async def get_finance(self, as_of: date) -> FinanceSignals: ...
    async def get_sales(self, as_of: date) -> SalesSignals: ...
    async def get_inventory(self) -> InventorySignals: ...
    async def get_inventory_health(self) -> StockHealthSignals: ...
    async def get_crm(self, as_of: date) -> CrmSignals: ...


@dataclass(frozen=True, slots=True)
class _ListPage:
    """One envelope page plus the pagination fact."""

    items: list[object]
    total_pages: int


class HttpCoreGateway:
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

    async def get_finance(self, as_of: date) -> FinanceSignals:
        balance = await self._get_data(
            "/finance/reports/balance-sheet", {"as_of": as_of.isoformat()}
        )
        aging = await self._get_data("/finance/reports/ar-aging", {"as_of": as_of.isoformat()})

        cash = _sum_for_code(balance.get("assets"), _CASH_CODES)
        payables = _sum_section(balance.get("liabilities"))

        total_ar = Decimal("0")
        buckets: dict[str, Decimal] = {}
        raw_buckets = aging.get("buckets")
        if isinstance(raw_buckets, list):
            for b in raw_buckets:
                if isinstance(b, dict):
                    key = str(b.get("bucket") or "current")
                    amount = _money(b.get("amount"))
                    buckets[key] = amount
                    total_ar += amount
        if not buckets:
            total_ar = _money(aging.get("total_ar"))

        return FinanceSignals(
            cash_balance=cash,
            total_ar=total_ar,
            ar_buckets=buckets,
            payables=payables,
            net_income=Decimal("0"),
        )

    async def get_sales(self, as_of: date) -> SalesSignals:
        confirmed = Decimal("0")
        for page in range(1, _MAX_CATALOG_PAGES + 1):
            page_data = await self._get_list("/sales/orders", page=page)
            for item in page_data.items:
                if isinstance(item, dict) and item.get("status") == "confirmed":
                    confirmed += _money(item.get("total"))
            if page >= page_data.total_pages:
                break
        return SalesSignals(confirmed_unfulfilled_value=confirmed)

    async def get_inventory(self) -> InventorySignals:
        products: list[object] = []
        for page in range(1, _MAX_CATALOG_PAGES + 1):
            page_data = await self._get_list("/inventory/products", page=page)
            products.extend(page_data.items)
            if page >= page_data.total_pages:
                break

        stock_by_product: dict[uuid.UUID, Decimal] = {}
        for page in range(1, _MAX_CATALOG_PAGES + 1):
            page_data = await self._get_list("/inventory/stock", page=page)
            for item in page_data.items:
                if isinstance(item, dict):
                    pid = _to_uuid(item.get("product_id"))
                    qty = _money(item.get("qty_on_hand"))
                    stock_by_product[pid] = stock_by_product.get(pid, Decimal("0")) + qty
            if page >= page_data.total_pages:
                break

        low_stock = 0
        stock_out = 0
        for prod in products:
            if not isinstance(prod, dict):
                continue
            pid = _to_uuid(prod.get("id"))
            reorder = _money(prod.get("reorder_point"))
            on_hand = stock_by_product.get(pid, Decimal("0"))
            if on_hand <= Decimal("0"):
                stock_out += 1
            elif on_hand <= reorder:
                low_stock += 1

        return InventorySignals(
            stock_out_count=stock_out,
            low_stock_count=low_stock,
            total_sku_count=len(products),
        )

    async def get_inventory_health(self) -> StockHealthSignals:
        summary = await self._get_data("/inventory/health/summary", {"days": "90"})
        return StockHealthSignals(
            dead_stock_count=_to_int(summary.get("dead_stock_count")),
            slow_mover_count=_to_int(summary.get("slow_mover_count")),
            tied_up_capital=_money(summary.get("tied_up_capital")),
        )

    async def get_crm(self, as_of: date) -> CrmSignals:
        items: list[object] = []
        for page in range(1, _MAX_CATALOG_PAGES + 1):
            page_data = await self._get_list("/crm/opportunities", page=page)
            items.extend(page_data.items)
            if page >= page_data.total_pages:
                break

        won = 0
        lost = 0
        open_count = 0
        won_recent = 0
        cutoff_date = as_of - timedelta(days=_RECENT_WIN_DAYS)
        for item in items:
            if not isinstance(item, dict):
                continue
            stage = str(item.get("stage") or "")
            won_at = _parse_dt(item.get("won_at"))
            lost_at = _parse_dt(item.get("lost_at"))
            if stage in ("won", "closed_won") or (won_at is not None):
                won += 1
                if won_at is not None and won_at.date() >= cutoff_date:
                    won_recent += 1
            elif stage in ("lost", "closed_lost") or (lost_at is not None):
                lost += 1
            else:
                open_count += 1

        total_decided = won + lost
        win_rate = (Decimal(won) / Decimal(total_decided)) if total_decided else Decimal("0")
        return CrmSignals(
            open_opportunities=open_count,
            won_recent_days=won_recent,
            win_rate=win_rate.quantize(Decimal("0.001")),
        )

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _create_client(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout)

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, object]:
        try:
            async with self._create_client(settings.INVENTORY_SERVICE_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1{path}",
                    params=params,
                    headers=self._headers(),
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("narrator_gateway_unreachable", path=path)
            raise AiUnavailableError("Core service is temporarily unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("narrator_gateway_bad_body", path=path)
            raise AiUnavailableError("Core service returned an unusable response") from exc
        if not isinstance(payload, dict):
            raise AiUnavailableError("Core service returned an unusable response")
        return payload

    async def _get_data(self, path: str, params: dict[str, str]) -> dict[str, object]:
        payload = await self._get(path, params)
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    async def _get_list(self, path: str, *, page: int) -> _ListPage:
        params = {"page": str(page), "page_size": str(_CATALOG_PAGE_SIZE)}
        payload = await self._get(path, params)
        data = payload.get("data")
        items = data if isinstance(data, list) else []
        meta = payload.get("meta")
        total_pages = meta.get("total_pages") if isinstance(meta, dict) else None
        if not isinstance(total_pages, int):
            total_pages = 1
        return _ListPage(items=items, total_pages=total_pages)


def _money(value: object) -> Decimal:
    """Normalize an amount that may be a number or a ``[amount, currency]`` tuple."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")
    if isinstance(value, (list, tuple)) and value:
        return _money(value[0])
    return Decimal("0")


def _to_uuid(value: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return uuid.uuid4()


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_int(value: object) -> int:
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return 0


def _sum_for_code(lines: object, codes: frozenset[str]) -> Decimal:
    if not isinstance(lines, list):
        return Decimal("0")
    total = Decimal("0")
    for line in lines:
        if isinstance(line, dict) and str(line.get("code") or "") in codes:
            total += _money(line.get("balance"))
    return total


def _sum_section(lines: object) -> Decimal:
    if not isinstance(lines, list):
        return Decimal("0")
    return sum(
        (_money(line.get("balance")) for line in lines if isinstance(line, dict)), Decimal("0")
    )
