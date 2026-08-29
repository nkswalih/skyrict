"""Unit tests for the demand forecasting calculator."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_agent.features.forecast.calculator import compute_forecasts
from ai_agent.features.nl_query.gateway import MovementRow, ProductRef

PRODUCT_ID = uuid.uuid4()
WAREHOUSE_ID = uuid.uuid4()


def _product() -> ProductRef:
    return ProductRef(
        id=PRODUCT_ID,
        sku="WIDGET-001",
        name="Widget",
        reorder_point=Decimal(20),
        cost_price=Decimal("5.00"),
    )


def _issue(hours_ago: float, qty: Decimal = Decimal(-10)) -> MovementRow:
    return MovementRow(
        id=uuid.uuid4(),
        product_id=PRODUCT_ID,
        warehouse_id=WAREHOUSE_ID,
        movement_type="issue",
        qty=qty,
        created_at=datetime.now(tz=UTC) - timedelta(hours=hours_ago),
        ref_id=None,
    )


class TestComputeForecasts:
    def test_three_horizons_returned(self) -> None:
        results = compute_forecasts(product=_product(), movements=[], qty_on_hand=Decimal(100))
        assert len(results) == 3
        assert [r.horizon_weeks for r in results] == [4, 8, 12]

    def test_no_demand_yields_zero_avg_daily(self) -> None:
        results = compute_forecasts(product=_product(), movements=[], qty_on_hand=Decimal(100))
        for r in results:
            assert r.avg_daily_demand == Decimal("0.00")
            assert r.weeks_of_supply is None
            assert r.stockout_date is None

    def test_demand_computed_from_issues(self) -> None:
        movements = [_issue(hours_ago=i * 20, qty=Decimal(-5)) for i in range(10)]
        results = compute_forecasts(
            product=_product(), movements=movements, qty_on_hand=Decimal(200)
        )
        four_week = next(r for r in results if r.horizon_weeks == 4)
        assert four_week.avg_daily_demand > Decimal("0")

    def test_weeks_of_supply_computed_when_demand_exists(self) -> None:
        movements = [_issue(hours_ago=i * 10, qty=Decimal(-2)) for i in range(15)]
        results = compute_forecasts(
            product=_product(), movements=movements, qty_on_hand=Decimal(100)
        )
        four_week = next(r for r in results if r.horizon_weeks == 4)
        assert four_week.weeks_of_supply is not None
        assert four_week.stockout_date is not None

    def test_different_product_movements_excluded(self) -> None:
        other_id = uuid.uuid4()
        other_movements = [
            MovementRow(
                id=uuid.uuid4(),
                product_id=other_id,
                warehouse_id=WAREHOUSE_ID,
                movement_type="issue",
                qty=Decimal(-50),
                created_at=datetime.now(tz=UTC) - timedelta(hours=1),
                ref_id=None,
            )
        ]
        results = compute_forecasts(
            product=_product(), movements=other_movements, qty_on_hand=Decimal(100)
        )
        for r in results:
            assert r.avg_daily_demand == Decimal("0.00")
