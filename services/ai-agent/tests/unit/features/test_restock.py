"""Unit tests for the restock calculator and scan/review service logic."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from ai_agent.features.nl_query.gateway import ProductRef, StockLevelRow
from ai_agent.features.restock.calculator import compute_suggestion
from ai_agent.features.restock.service import RestockService

PRODUCT_ID = uuid.uuid4()
WAREHOUSE_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _product(cost: Decimal | None = Decimal("100.00")) -> ProductRef:
    return ProductRef(
        id=PRODUCT_ID,
        sku="LAPTOP-CHG-001",
        name="Laptop Charger 65W",
        reorder_point=Decimal(10),
        cost_price=cost,
    )


class TestCalculator:
    def test_v1_formula_quantity_and_cost(self) -> None:
        draft = compute_suggestion(
            product=_product(), warehouse_id=WAREHOUSE_ID, qty_on_hand=Decimal(3)
        )
        assert draft.suggested_qty == Decimal(20)  # reorder_point * 2 (spec §3.2)
        assert draft.estimated_cost == Decimal("2000.00")  # 20 * 100.00, local only
        assert "below reorder point" in draft.reason.lower()

    def test_confidence_rises_with_deficit_and_is_capped(self) -> None:
        shallow = compute_suggestion(
            product=_product(), warehouse_id=WAREHOUSE_ID, qty_on_hand=Decimal(9)
        )
        deep = compute_suggestion(
            product=_product(), warehouse_id=WAREHOUSE_ID, qty_on_hand=Decimal(-10)
        )
        assert shallow.confidence is not None and deep.confidence is not None
        assert deep.confidence > shallow.confidence
        assert deep.confidence <= Decimal("0.95")

    def test_missing_cost_yields_null_estimate(self) -> None:
        draft = compute_suggestion(
            product=_product(cost=None), warehouse_id=WAREHOUSE_ID, qty_on_hand=Decimal(3)
        )
        assert draft.estimated_cost is None


class FakeGateway:
    def __init__(self) -> None:
        self.products = [_product()]
        self.stock = [
            StockLevelRow(
                product_id=PRODUCT_ID,
                warehouse_id=WAREHOUSE_ID,
                qty_on_hand=Decimal(3),
                qty_reserved=Decimal(0),
            ),
            StockLevelRow(
                product_id=uuid.uuid4(),
                warehouse_id=WAREHOUSE_ID,
                qty_on_hand=Decimal(999),
                qty_reserved=Decimal(0),  # healthy
            ),
        ]

    async def list_products(self):
        return self.products

    async def get_stock_levels(self, *, product_id=None, warehouse_id=None):
        return self.stock

    async def list_movements(self, *, product_id=None, warehouse_id=None, movement_type=None):
        return []


class FakeSuggestions:
    def __init__(self, pending_pairs=None) -> None:
        self.pending_pairs = pending_pairs or set()
        self.created: list[dict[str, object]] = []

    async def list_by_status(self, *, tenant_id, status="pending", limit=100):
        class Row:
            pass

        rows = []
        for pair in self.pending_pairs:
            r = Row()
            r.product_id, r.warehouse_id = pair
            rows.append(r)
        return rows, len(rows)

    async def create_pending(self, **kwargs):
        from types import SimpleNamespace

        row = SimpleNamespace(**kwargs, id=uuid.uuid4())
        self.created.append(kwargs)
        return row


class FakeAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def log(self, *, action, **kwargs):
        self.actions.append(action)


def _make_service(pending_pairs=None):
    gateway = FakeGateway()

    async def factory():
        return gateway

    suggestions = FakeSuggestions(pending_pairs)
    audit = FakeAudit()
    service = RestockService(gateway_factory=factory, suggestions=suggestions, audit=audit)
    return service, suggestions, audit


class TestScan:
    async def test_creates_pending_for_below_reorder_only(self) -> None:
        service, repo, audit = _make_service()
        report = await service.run_scan(tenant_id=TENANT_ID)

        assert report.created == 1
        assert report.considered == 2
        created = repo.created[0]
        assert created["product_id"] == PRODUCT_ID
        assert created["suggested_qty"] == Decimal(20)
        # Audit event recorded with the Appendix B vocabulary.
        assert any(a.endswith("suggestion.created") for a in audit.actions)

    async def test_skips_pairs_with_existing_pending_suggestion(self) -> None:
        service, repo, _audit = _make_service(pending_pairs={(PRODUCT_ID, WAREHOUSE_ID)})
        report = await service.run_scan(tenant_id=TENANT_ID)

        assert report.created == 0
        assert report.skipped_pending == 1
        assert repo.created == []


class TestReview:
    async def _seeded_row(self):
        from datetime import UTC, datetime
        from types import SimpleNamespace

        return SimpleNamespace(
            id=uuid.uuid4(),
            status="pending",
            reviewed_by=None,
            reviewed_at=None,
            review_note=None,
            created_at=datetime.now(tz=UTC),
        )

    async def test_approve_transitions_pending_row(self) -> None:
        service, _repo, audit = _make_service()
        row = await self._seeded_row()

        captured = {}

        async def fake_get(*, tenant_id, suggestion_id):
            return row

        async def fake_record(**kwargs):
            captured.update(kwargs)
            kwargs["row"].status = kwargs["status"]
            return kwargs["row"]

        service._suggestions.get_for_review = fake_get
        service._suggestions.record_review = fake_record

        await service.review(
            tenant_id=TENANT_ID,
            user_id=uuid.uuid4(),
            suggestion_id=row.id,
            decision="approved",
            note="ok",
        )

        assert captured["status"] == "approved"
        assert any(a.endswith("suggestion.approved") for a in audit.actions)

    async def test_double_review_rejected_as_conflict(self) -> None:
        from types import SimpleNamespace

        from skyrict_common.exceptions import ConflictError

        service, _repo, _audit = _make_service()
        done = SimpleNamespace(status="approved", id=uuid.uuid4())

        async def fake_get(*, tenant_id, suggestion_id):
            return done

        service._suggestions.get_for_review = fake_get

        with pytest.raises(ConflictError):
            await service.review(
                tenant_id=TENANT_ID,
                user_id=uuid.uuid4(),
                suggestion_id=done.id,
                decision="rejected",
                note=None,
            )
