"""Demand forecasting calculator - pure functions, no I/O.

Computes per-SKU moving-average forecasts over configurable horizons
(4/8/12 weeks), weeks-of-supply, and estimated stockout dates from
raw movement data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from ai_agent.features.nl_query.gateway import MovementRow, ProductRef


@dataclass(frozen=True, slots=True)
class ForecastResult:
    product_id: uuid.UUID
    horizon_weeks: int
    avg_daily_demand: Decimal
    weeks_of_supply: Decimal | None
    stockout_date: datetime | None


def compute_forecasts(
    *,
    product: ProductRef,
    movements: list[MovementRow],
    qty_on_hand: Decimal,
    horizons: tuple[int, ...] = (4, 8, 12),
) -> list[ForecastResult]:
    """Compute moving-average forecasts for one product across all horizons."""
    results = []
    for weeks in horizons:
        result = _compute_single_forecast(
            product=product,
            movements=movements,
            qty_on_hand=qty_on_hand,
            horizon_weeks=weeks,
        )
        results.append(result)
    return results


def _compute_single_forecast(
    *,
    product: ProductRef,
    movements: list[MovementRow],
    qty_on_hand: Decimal,
    horizon_weeks: int,
) -> ForecastResult:
    """Moving-average demand over one horizon, plus weeks-of-supply and stockout date."""
    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(weeks=horizon_weeks)

    # Filter to issue movements (demand) for this product within horizon.
    relevant = [
        m
        for m in movements
        if m.product_id == product.id
        and m.movement_type == "issue"
        and m.qty < 0
        and _as_utc(m.created_at) >= cutoff
    ]

    total_demand = Decimal(str(sum(abs(m.qty) for m in relevant))) if relevant else Decimal(0)
    horizon_days = horizon_weeks * 7
    avg_daily_demand = (
        (total_demand / horizon_days).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if horizon_days > 0
        else Decimal(0)
    )

    # Weeks of supply: how many weeks the current stock will last.
    weeks_of_supply: Decimal | None = None
    stockout_date: datetime | None = None
    if avg_daily_demand > 0:
        days_remaining = (qty_on_hand / avg_daily_demand).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        weeks_of_supply = (qty_on_hand / avg_daily_demand / 7).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        stockout_date = now + timedelta(days=int(days_remaining))

    return ForecastResult(
        product_id=product.id,
        horizon_weeks=horizon_weeks,
        avg_daily_demand=avg_daily_demand,
        weeks_of_supply=weeks_of_supply,
        stockout_date=stockout_date,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
