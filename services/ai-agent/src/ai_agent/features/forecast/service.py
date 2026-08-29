"""Forecast service - orchestrates forecast computation for all SKUs."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from ai_agent.features.nl_query.gateway import InventoryGatewayPort

logger = structlog.get_logger("ai_agent.forecast_service")


class ForecastService:
    def __init__(self, *, gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]]) -> None:
        self._gateway_factory = gateway_factory

    async def get_forecast(self, *, product_id: uuid.UUID) -> list[dict[str, object]]:
        from ai_agent.features.forecast.calculator import compute_forecasts

        gateway = await self._gateway_factory()
        products = await gateway.list_products()
        product = next((p for p in products if p.id == product_id), None)
        if product is None:
            from skyrict_common.exceptions import NotFoundError

            raise NotFoundError("Product not found")

        levels = await gateway.get_stock_levels(product_id=product_id)
        qty_on_hand = sum((row.qty_on_hand for row in levels), Decimal(0))
        movements = await gateway.list_movements(product_id=product_id)

        forecasts = compute_forecasts(
            product=product,
            movements=movements,
            qty_on_hand=qty_on_hand,
        )
        return [
            {
                "product_id": str(f.product_id),
                "horizon_weeks": f.horizon_weeks,
                "avg_daily_demand": str(f.avg_daily_demand),
                "weeks_of_supply": str(f.weeks_of_supply)
                if f.weeks_of_supply is not None
                else None,
                "stockout_date": f.stockout_date.isoformat() if f.stockout_date else None,
            }
            for f in forecasts
        ]
