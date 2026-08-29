"""Unit tests for the forecast service (gateway orchestration layer).

``get_forecast`` is the composition point between the inventory gateway and the
pure forecasting calculator. The calculator is covered exhaustively in
test_forecast.py; here we lock in the service contract: product resolution
(unknown id -> typed 404) and a full compute path that USES the real Decimal
arithmetic (regression: Decimal was used without import, see SKY-68).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai_agent.features.forecast.service import ForecastService
from ai_agent.features.nl_query.gateway import (
    InventoryGatewayPort,
    MovementRow,
    ProductRef,
    StockLevelRow,
    WarehouseRef,
)
from skyrict_common.exceptions import NotFoundError

PRODUCT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
WAREHOUSE_ID = uuid.UUID("10000000-0000-0000-0000-000000000002")


class FakeGateway:
    """In-memory InventoryGatewayPort bound to the service's needs."""

    def __init__(self) -> None:
        self.products = [
            ProductRef(
                id=PRODUCT_ID,
                sku="WIDGET-002",
                name="Widget 2",
                reorder_point=Decimal(20),
                cost_price=Decimal("5.00"),
            )
        ]
        self.warehouses = [WarehouseRef(id=WAREHOUSE_ID, name="Main")]
        self.stock_levels = [
            StockLevelRow(
                product_id=PRODUCT_ID,
                warehouse_id=WAREHOUSE_ID,
                qty_on_hand=Decimal(100),
                qty_reserved=Decimal(0),
            )
        ]
        self.movements = [
            MovementRow(
                id=uuid.uuid4(),
                product_id=PRODUCT_ID,
                warehouse_id=WAREHOUSE_ID,
                movement_type="issue",
                qty=Decimal(-4),
                created_at=datetime.now(tz=UTC) - timedelta(hours=24),
            )
        ]

    async def list_products(self) -> list[ProductRef]:
        return self.products

    async def list_warehouses(self) -> list[WarehouseRef]:
        return self.warehouses

    async def get_stock_levels(
        self,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> list[StockLevelRow]:
        return [
            row
            for row in self.stock_levels
            if (product_id is None or row.product_id == product_id)
            and (warehouse_id is None or row.warehouse_id == warehouse_id)
        ]

    async def list_movements(
        self,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        movement_type: str | None = None,
    ) -> list[MovementRow]:
        return [
            row
            for row in self.movements
            if (product_id is None or row.product_id == product_id)
            and (warehouse_id is None or row.warehouse_id == warehouse_id)
            and (movement_type is None or row.movement_type == movement_type)
        ]


def _service(gateway: FakeGateway) -> ForecastService:
    async def factory() -> InventoryGatewayPort:
        return gateway

    return ForecastService(gateway_factory=factory)


class TestGetForecast:
    async def test_computes_forecasts_with_real_decimal_arithmetic(self) -> None:
        items = await _service(FakeGateway()).get_forecast(product_id=PRODUCT_ID)

        assert len(items) == 3
        assert [item["horizon_weeks"] for item in items] == [4, 8, 12]
        # Demand from the single issue drives a non-zero (decimal) average.
        assert Decimal(items[0]["avg_daily_demand"]) > Decimal("0")
        assert all(item["product_id"] == str(PRODUCT_ID) for item in items)

    async def test_no_stock_levels_or_movements_still_computes_zero_demand(self) -> None:
        gateway = FakeGateway()
        gateway.stock_levels = []
        gateway.movements = []

        items = await _service(gateway).get_forecast(product_id=PRODUCT_ID)

        assert len(items) == 3
        assert all(Decimal(item["avg_daily_demand"]) == Decimal("0.00") for item in items)

    async def test_unknown_product_raises_typed_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            await _service(FakeGateway()).get_forecast(product_id=uuid.uuid4())
