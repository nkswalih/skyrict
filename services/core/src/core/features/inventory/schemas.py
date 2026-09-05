"""Inventory schemas - the API boundary (requests and responses).

Money is a pure-domain value object (``core.domain.value_objects.Money``), so
the HTTP boundary carries it as a ``(amount, currency)`` tuple. Inputs keep
Decimal amounts; outputs serialize amounts as strings so JSON never loses
precision. Response models are built from domain entities via ``from_entity``
because ``Money`` is not pydantic-serializable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from core.core.config import settings
from core.domain.entities import (
    DeadStockItem,
    MovementTrendPoint,
    Product,
    SlowMoverItem,
    StockHealthSummary,
    StockLevel,
    StockMovement,
    Warehouse,
)
from core.domain.value_objects import Money, StockMovementType

# Request money shape: (amount, currency) e.g. ``[12.50, "USD"]``.
type MoneyInput = tuple[Decimal, str]
# Response money shape: (amount-as-string, currency) - exact decimals.
type MoneyOutput = tuple[str, str]


def money_input(value: MoneyInput | None) -> Money:
    """Convert a request money tuple (or None) into a validated ``Money``."""
    if value is None:
        return Money.zero(settings.DEFAULT_CURRENCY)
    amount, currency = value
    return Money(amount=amount, currency=currency)


def money_output(value: Money) -> MoneyOutput:
    """Serialize a ``Money`` as ``(amount-string, currency)`` for responses."""
    return (str(value.amount), value.currency)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class ProductCreate(BaseModel):
    """POST /inventory/products - create a product.

    ``ref_id`` is deliberately NOT here: product creation is not a ledger
    mutation, so it needs no idempotency probe.
    """

    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=32)
    cost_price: MoneyInput | None = None
    sell_price: MoneyInput | None = None
    reorder_point: Decimal = Field(default=Decimal("0"), ge=0)


class ProductUpdate(BaseModel):
    """PATCH /inventory/products/{id} - partial update of a product.

    Every field is optional; only the fields present in the body are applied.
    ``sku``, when provided, must stay unique within the tenant (excluding the
    product being edited).
    """

    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=32)
    cost_price: MoneyInput | None = None
    sell_price: MoneyInput | None = None
    reorder_point: Decimal | None = Field(default=None, ge=0)


class ProductResponse(BaseModel):
    """Product data returned in API responses."""

    id: uuid.UUID
    sku: str
    name: str
    category: str | None
    unit: str | None
    cost_price: MoneyOutput
    sell_price: MoneyOutput
    reorder_point: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, product: Product) -> ProductResponse:
        assert product.id is not None and product.created_at is not None
        assert product.updated_at is not None
        return cls(
            id=product.id,
            sku=product.sku,
            name=product.name,
            category=product.category,
            unit=product.unit,
            cost_price=money_output(product.cost_price),
            sell_price=money_output(product.sell_price),
            reorder_point=str(product.reorder_point),
            is_active=product.is_active,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------


class WarehouseCreate(BaseModel):
    """POST /inventory/warehouses - create a warehouse."""

    name: str = Field(..., min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=255)


class WarehouseUpdate(BaseModel):
    """PATCH /inventory/warehouses/{id} - partial update of a warehouse."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=255)


class WarehouseResponse(BaseModel):
    """Warehouse data returned in API responses."""

    id: uuid.UUID
    name: str
    location: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, warehouse: Warehouse) -> WarehouseResponse:
        assert warehouse.id is not None and warehouse.created_at is not None
        assert warehouse.updated_at is not None
        return cls(
            id=warehouse.id,
            name=warehouse.name,
            location=warehouse.location,
            is_active=warehouse.is_active,
            created_at=warehouse.created_at,
            updated_at=warehouse.updated_at,
        )


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------


class StockAdjustmentCreate(BaseModel):
    """POST /inventory/stock/adjustments - record a signed stock adjustment.

    ``qty`` is signed (+ receive, - issue). ``reason`` is required (service-
    enforced). ``ref_id`` is the idempotency key: replaying the same
    ``(ref_id, warehouse_id)`` is rejected with 409.
    """

    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    qty: Decimal = Field(..., description="signed delta (+ receive, - issue)")
    reason: str = Field(..., min_length=1, max_length=255)
    ref_id: str = Field(..., min_length=1, max_length=64)


class StockTransferCreate(BaseModel):
    """POST /inventory/stock/transfers - move stock between two warehouses.

    ``ref_id`` is shared by the source (negative) and destination (positive)
    movement pair, so the atomic transfer is replay-safe.
    """

    product_id: uuid.UUID
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    qty: Decimal = Field(..., gt=0)
    ref_id: str = Field(..., min_length=1, max_length=64)


class StockReserveCreate(BaseModel):
    """POST /inventory/stock/reservations - reserve stock for a pending order.

    ``qty`` must be positive and cannot exceed available (on-hand minus already
    reserved).  The caller-supplied ``ref_id`` is replay-safe.
    """

    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    qty: Decimal = Field(..., gt=0)
    ref_id: str = Field(..., min_length=1, max_length=64)


class StockReleaseCreate(BaseModel):
    """POST /inventory/stock/releases - release previously reserved stock.

    ``qty`` must be positive and cannot exceed the currently reserved quantity.
    """

    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    qty: Decimal = Field(..., gt=0)
    ref_id: str = Field(..., min_length=1, max_length=64)


class StockLevelResponse(BaseModel):
    """Materialized current stock for one product in one warehouse."""

    id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    qty_on_hand: str
    qty_reserved: str
    updated_at: datetime

    @classmethod
    def from_entity(cls, level: StockLevel) -> StockLevelResponse:
        assert level.id is not None and level.updated_at is not None
        return cls(
            id=level.id,
            product_id=level.product_id,
            warehouse_id=level.warehouse_id,
            qty_on_hand=str(level.qty_on_hand),
            qty_reserved=str(level.qty_reserved),
            updated_at=level.updated_at,
        )


class StockMovementResponse(BaseModel):
    """One immutable ledger entry."""

    id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    movement_type: StockMovementType
    qty: str
    ref_type: str
    ref_id: str
    created_at: datetime

    @classmethod
    def from_entity(cls, movement: StockMovement) -> StockMovementResponse:
        assert movement.id is not None and movement.created_at is not None
        return cls(
            id=movement.id,
            product_id=movement.product_id,
            warehouse_id=movement.warehouse_id,
            movement_type=movement.movement_type,
            qty=str(movement.qty),
            ref_type=movement.ref_type,
            ref_id=movement.ref_id,
            created_at=movement.created_at,
        )


class TransferResponse(BaseModel):
    """The atomic transfer pair - both movements or none."""

    from_movement: StockMovementResponse
    to_movement: StockMovementResponse

    @classmethod
    def from_entities(
        cls, from_movement: StockMovement, to_movement: StockMovement
    ) -> TransferResponse:
        return cls(
            from_movement=StockMovementResponse.from_entity(from_movement),
            to_movement=StockMovementResponse.from_entity(to_movement),
        )


class AlertResponse(BaseModel):
    """A product/warehouse currently at or below its reorder point."""

    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    sku: str
    name: str
    qty_on_hand: str
    reorder_point: str

    @classmethod
    def from_entities(cls, level: StockLevel, product: Product) -> AlertResponse:
        return cls(
            product_id=level.product_id,
            warehouse_id=level.warehouse_id,
            sku=product.sku,
            name=product.name,
            qty_on_hand=str(level.qty_on_hand),
            reorder_point=str(product.reorder_point),
        )


# ---------------------------------------------------------------------------
# Stock-health analytics (INV-ANL-001)
# ---------------------------------------------------------------------------


class DeadStockItemResponse(BaseModel):
    """A product with on-hand stock but no outbound movement in the window.

    Cost fields are only populated when the caller holds ``erp.inventory.cost``
    (the router blanks them otherwise) — valuations are server-side only.
    """

    product_id: uuid.UUID
    sku: str
    name: str
    qty_on_hand: str
    warehouse_id: uuid.UUID | None = None
    cost_price: MoneyOutput | None = None
    tied_up_value: MoneyOutput | None = None
    last_outbound_at: datetime | None = None

    @classmethod
    def from_entity(cls, item: DeadStockItem, *, include_cost: bool) -> DeadStockItemResponse:
        return cls(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            qty_on_hand=str(item.qty_on_hand),
            warehouse_id=item.warehouse_id,
            cost_price=money_output(item.cost_price) if include_cost else None,
            tied_up_value=money_output(item.tied_up_value) if include_cost else None,
            last_outbound_at=item.last_outbound_at,
        )


class SlowMoverItemResponse(BaseModel):
    """A bottom-quartile turnover item with a suggested-markdown advice flag."""

    product_id: uuid.UUID
    sku: str
    name: str
    qty_on_hand: str
    turnover_ratio: str
    warehouse_id: uuid.UUID | None = None
    cost_price: MoneyOutput | None = None
    carrying_cost: MoneyOutput | None = None
    last_outbound_at: datetime | None = None
    suggest_markdown: bool = False

    @classmethod
    def from_entity(cls, item: SlowMoverItem, *, include_cost: bool) -> SlowMoverItemResponse:
        return cls(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            qty_on_hand=str(item.qty_on_hand),
            turnover_ratio=str(item.turnover_ratio),
            warehouse_id=item.warehouse_id,
            cost_price=money_output(item.cost_price) if include_cost else None,
            carrying_cost=money_output(item.carrying_cost) if include_cost else None,
            last_outbound_at=item.last_outbound_at,
            suggest_markdown=item.suggest_markdown,
        )


class MovementTrendPointResponse(BaseModel):
    """One week's stacked receipts/issues/adjustments per warehouse."""

    period_start: datetime
    warehouse_id: uuid.UUID | None = None
    receipts: str
    issues: str
    adjustments: str

    @classmethod
    def from_entity(cls, point: MovementTrendPoint) -> MovementTrendPointResponse:
        return cls(
            period_start=point.period_start,
            warehouse_id=point.warehouse_id,
            receipts=str(point.receipts),
            issues=str(point.issues),
            adjustments=str(point.adjustments),
        )


class StockHealthSummaryResponse(BaseModel):
    """Aggregate stock-health metrics fed to the SKY-63 narrator digest."""

    total_sku_count: int
    low_stock_count: int
    dead_stock_count: int
    slow_mover_count: int
    tied_up_capital: MoneyOutput | None = None

    @classmethod
    def from_entity(
        cls, summary: StockHealthSummary, *, include_cost: bool
    ) -> StockHealthSummaryResponse:
        return cls(
            total_sku_count=summary.total_sku_count,
            low_stock_count=summary.low_stock_count,
            dead_stock_count=summary.dead_stock_count,
            slow_mover_count=summary.slow_mover_count,
            tied_up_capital=money_output(summary.tied_up_capital) if include_cost else None,
        )
