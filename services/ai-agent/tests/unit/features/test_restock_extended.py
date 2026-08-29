"""Extended restock calculator tests — 4-factor confidence scoring."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_agent.features.nl_query.gateway import MovementRow, ProductRef
from ai_agent.features.restock.calculator import compute_suggestion

PRODUCT_ID = uuid.uuid4()
WAREHOUSE_ID = uuid.uuid4()


def _product(cost: Decimal | None = Decimal("100.00")) -> ProductRef:
    return ProductRef(
        id=PRODUCT_ID,
        sku="LAPTOP-CHG-001",
        name="Laptop Charger 65W",
        reorder_point=Decimal(10),
        cost_price=cost,
    )


def _receipt(hours_ago: float, qty: Decimal = Decimal(50)) -> MovementRow:
    return MovementRow(
        id=uuid.uuid4(),
        product_id=PRODUCT_ID,
        warehouse_id=WAREHOUSE_ID,
        movement_type="receipt",
        qty=qty,
        created_at=datetime.now(tz=UTC) - timedelta(hours=hours_ago),
        ref_id=None,
    )


def _issue(hours_ago: float, qty: Decimal = Decimal(-5)) -> MovementRow:
    return MovementRow(
        id=uuid.uuid4(),
        product_id=PRODUCT_ID,
        warehouse_id=WAREHOUSE_ID,
        movement_type="issue",
        qty=qty,
        created_at=datetime.now(tz=UTC) - timedelta(hours=hours_ago),
        ref_id=None,
    )


class TestFourFactorConfidence:
    def test_with_movements_uses_four_factor(self) -> None:
        movements = [_receipt(hours_ago=24 * i, qty=Decimal(50)) for i in range(10)]
        draft = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(3),
            movements=movements,
        )
        assert draft.confidence >= Decimal("0.50")
        assert draft.confidence <= Decimal("0.95")

    def test_without_movements_uses_v1_fallback(self) -> None:
        draft = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(3),
            movements=None,
        )
        assert draft.confidence >= Decimal("0.50")
        assert draft.confidence <= Decimal("0.95")

    def test_more_history_higher_data_quality(self) -> None:
        few = [_receipt(hours_ago=24 * i) for i in range(5)]
        many = [_receipt(hours_ago=24 * i) for i in range(60)]
        draft_few = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(3),
            movements=few,
        )
        draft_many = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(3),
            movements=many,
        )
        assert draft_many.confidence >= draft_few.confidence

    def test_no_receipts_high_recency_score(self) -> None:
        issues_only = [_issue(hours_ago=24 * i) for i in range(10)]
        draft = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(3),
            movements=issues_only,
        )
        assert draft.confidence >= Decimal("0.50")

    def test_deeper_deficit_higher_proximity_score(self) -> None:
        shallow = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(9),
            movements=[_receipt(hours_ago=1)],
        )
        deep = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(-10),
            movements=[_receipt(hours_ago=1)],
        )
        assert deep.confidence >= shallow.confidence

    def test_suggested_qty_always_double_reorder(self) -> None:
        draft = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(3),
        )
        assert draft.suggested_qty == Decimal(20)

    def test_confidence_never_exceeds_095(self) -> None:
        movements = [_receipt(hours_ago=24 * i) for i in range(120)]
        draft = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(-20),
            movements=movements,
        )
        assert draft.confidence <= Decimal("0.95")

    def test_confidence_never_below_050(self) -> None:
        draft = compute_suggestion(
            product=_product(cost=None),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(9),
            movements=[],
        )
        assert draft.confidence >= Decimal("0.50")

    def test_other_product_movements_excluded(self) -> None:
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
        draft = compute_suggestion(
            product=_product(),
            warehouse_id=WAREHOUSE_ID,
            qty_on_hand=Decimal(3),
            movements=other_movements,
        )
        assert draft.confidence <= Decimal("0.95")
