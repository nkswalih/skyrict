"""Signal extraction - collapse cross-module reads into a compact payload.

Separates DATA from PROSE: the service gathers raw signals, this module turns
them into the gold-signal dict the LLM narrates from, and decides whether the
day is "material" enough to narrate at all (empty days abstain instead of
producing boilerplate).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from ai_agent.features.narrator.gateway import (
        CrmSignals,
        FinanceSignals,
        InventorySignals,
        SalesSignals,
        StockHealthSignals,
    )


_MONEY_KEYS = frozenset(
    {
        "cash_balance",
        "total_ar",
        "payables",
        "net_income",
        "ar_over_90",
        "confirmed_unfulfilled_value",
    }
)


def build_signals_dict(
    *,
    as_of: date,
    finance: FinanceSignals,
    sales: SalesSignals,
    inventory: InventorySignals,
    inventory_health: StockHealthSignals,
    crm: CrmSignals,
) -> dict[str, object]:
    """Return a JSON-serializable gold-signal payload (money as strings)."""
    ar_over_90 = finance.ar_buckets.get("over_90", Decimal("0"))
    finance_payload: dict[str, object] = {
        "cash_balance": _amount(finance.cash_balance),
        "total_ar": _amount(finance.total_ar),
        "payables": _amount(finance.payables),
        "net_income": _amount(finance.net_income),
        "ar_over_90": _amount(ar_over_90),
    }
    sales_payload: dict[str, object] = {
        "confirmed_unfulfilled_value": _amount(sales.confirmed_unfulfilled_value)
    }
    inventory_payload: dict[str, object] = {
        "stock_out_count": inventory.stock_out_count,
        "low_stock_count": inventory.low_stock_count,
        "total_sku_count": inventory.total_sku_count,
    }
    if inventory_health is not None:
        inventory_payload.update(
            {
                "dead_stock_count": inventory_health.dead_stock_count,
                "slow_mover_count": inventory_health.slow_mover_count,
                "tied_up_capital": _amount(inventory_health.tied_up_capital),
            }
        )
    crm_payload: dict[str, object] = {
        "open_opportunities": crm.open_opportunities,
        "won_recent_days": crm.won_recent_days,
        "win_rate": _amount(crm.win_rate),
    }
    return {
        "as_of": as_of.isoformat(),
        "finance": finance_payload,
        "sales": sales_payload,
        "inventory": inventory_payload,
        "crm": crm_payload,
    }


def has_material_activity(signals: dict[str, object]) -> bool:
    """False when every module reports essentially empty/zero data.

    An empty day has nothing worth narrating; we abstain rather than let the
    LLM pad a digest with boilerplate.
    """
    finance = _section(signals, "finance")
    sales = _section(signals, "sales")
    inventory = _section(signals, "inventory")
    crm = _section(signals, "crm")

    finance_money = any(
        _money_gte(finance.get(k), Decimal("0.01")) for k in _MONEY_KEYS if k in finance
    )
    has_inventory_issues = (
        _int_val(inventory.get("stock_out_count")) > 0
        or _int_val(inventory.get("low_stock_count")) > 0
        or _int_val(inventory.get("dead_stock_count")) > 0
        or _int_val(inventory.get("slow_mover_count")) > 0
    )
    has_open_deals = (
        _int_val(crm.get("open_opportunities")) > 0 or _int_val(crm.get("won_recent_days")) > 0
    )
    has_sales_value = _money_gte(sales.get("confirmed_unfulfilled_value"), Decimal("0.01"))

    return bool(finance_money or has_inventory_issues or has_open_deals or has_sales_value)


def build_prompt(signals: dict[str, object]) -> str:
    """Human-friendly JSON prompt describing the day for narration."""
    return (
        "Here is today's cross-module ERP snapshot. Write a concise executive "
        "digest that connects the dots across Finance, Sales, Inventory and CRM. "
        "Be specific about numbers, flag anything unusual or risky (e.g. past-due "
        "receivables, stock-outs, low win rate), and keep it under ~120 words.\n\n"
        + json.dumps(signals, indent=2)
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _section(signals: dict[str, object], key: str) -> dict[str, object]:
    value = signals.get(key)
    return value if isinstance(value, dict) else {}


def _int_val(value: object) -> int:
    try:
        return int(str(value))
    except Exception:
        return 0


def _money_gte(value: object, floor: Decimal) -> bool:
    if value is None:
        return False
    try:
        return Decimal(str(value)) >= floor
    except Exception:
        return False
