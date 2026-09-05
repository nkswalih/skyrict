"""Inventory repository + service ports - persistence and business contracts.

Declares what the repository must offer so services depend on this Protocol
(hexagonal "port") rather than the concrete SQLAlchemy implementation. There is
deliberately NO update/delete for stock movements: the ledger is immutable.

``StockReservationPort`` is the contract CRM calls at order confirmation
(reserve/release/fulfil); ``InventoryServicePort`` is what the HTTP router
consumes. Both are implemented by ``core.features.inventory.service``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

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


class InventoryRepositoryPort(Protocol):
    """Persistence contract for products, warehouses, stock levels, movements."""

    # --- Products (soft-delete via is_active = false) ---
    async def create_product(self, product: Product) -> Product: ...

    async def get_product(self, product_id: uuid.UUID, tenant_id: uuid.UUID) -> Product | None: ...

    async def get_product_by_sku(self, sku: str, tenant_id: uuid.UUID) -> Product | None: ...

    async def update_product(
        self,
        product_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        sku: str | object = ...,
        name: str | object = ...,
        category: str | object | None = ...,
        unit: str | object | None = ...,
        cost_price: Money | object = ...,
        sell_price: Money | object = ...,
        reorder_point: Decimal | object = ...,
    ) -> Product | None: ...

    async def deactivate_product(
        self, product_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Product | None: ...

    async def reactivate_product(
        self, product_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Product | None: ...

    async def list_products(
        self,
        tenant_id: uuid.UUID,
        *,
        include_inactive: bool = False,
        category: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[Product]: ...

    async def count_products(
        self,
        tenant_id: uuid.UUID,
        *,
        include_inactive: bool = False,
        category: str | None = None,
    ) -> int: ...

    # --- Warehouses (soft-delete via is_active = false) ---
    async def create_warehouse(self, warehouse: Warehouse) -> Warehouse: ...

    async def get_warehouse(
        self, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Warehouse | None: ...

    async def update_warehouse(
        self,
        warehouse_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        name: str | object = ...,
        location: str | object | None = ...,
    ) -> Warehouse | None: ...

    async def deactivate_warehouse(
        self, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Warehouse | None: ...

    async def reactivate_warehouse(
        self, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Warehouse | None: ...

    async def list_warehouses(
        self,
        tenant_id: uuid.UUID,
        *,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[Warehouse]: ...

    async def count_warehouses(
        self, tenant_id: uuid.UUID, *, include_inactive: bool = False
    ) -> int: ...

    # --- Stock levels (materialized from the ledger) ---
    async def get_stock_level(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> StockLevel | None: ...

    async def recompute_stock_level(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> StockLevel: ...

    async def list_stock_levels(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[StockLevel]: ...

    async def count_stock_levels(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> int: ...

    async def sum_stock_by_product(
        self, product_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> tuple[Decimal, Decimal]: ...

    async def sum_stock_by_warehouse(
        self, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> tuple[Decimal, Decimal]: ...

    async def list_low_stock(
        self,
        tenant_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[tuple[StockLevel, Product]]: ...

    async def count_low_stock(self, tenant_id: uuid.UUID) -> int: ...

    # --- Guarded reservation updates (atomic row-lock) ---
    async def apply_reservation_qty(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, qty: Decimal, tenant_id: uuid.UUID
    ) -> bool: ...

    async def apply_release_qty(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, qty: Decimal, tenant_id: uuid.UUID
    ) -> bool: ...

    async def apply_consume_qty(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, qty: Decimal, tenant_id: uuid.UUID
    ) -> bool: ...

    # --- Movements (immutable ledger - no update, no delete) ---
    async def add_movement(self, movement: StockMovement) -> StockMovement: ...

    async def get_movement_by_ref(
        self,
        ref_type: str,
        ref_id: str,
        warehouse_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> StockMovement | None: ...

    async def list_movements(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        movement_type: StockMovementType | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[StockMovement]: ...

    async def count_movements(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        movement_type: StockMovementType | None = None,
    ) -> int: ...

    # --- Stock-health analytics (INV-ANL-001) ---
    async def dead_stock(
        self,
        tenant_id: uuid.UUID,
        *,
        days: int = 90,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[DeadStockItem]: ...

    async def count_dead_stock(self, tenant_id: uuid.UUID, *, days: int = 90) -> int: ...

    async def slow_movers(
        self,
        tenant_id: uuid.UUID,
        *,
        window_days: int = 180,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[SlowMoverItem]: ...

    async def count_slow_movers(self, tenant_id: uuid.UUID, *, window_days: int = 180) -> int: ...

    async def movement_trends(
        self,
        tenant_id: uuid.UUID,
        *,
        warehouse_id: uuid.UUID | None = None,
        weeks: int = 13,
    ) -> Sequence[MovementTrendPoint]: ...

    async def health_summary(
        self, tenant_id: uuid.UUID, *, days: int = 90
    ) -> StockHealthSummary: ...

    async def commit(self) -> None: ...


class StockReservationPort(Protocol):
    """Reservation contract CRM calls at order confirmation.

    Invariants (Rule 5 / §5.4):
      - ``reserve_stock`` never lets ``qty_reserved`` exceed ``qty_on_hand``
        (raises ``InsufficientStockError`` otherwise);
      - ``release_reservation`` never drops ``qty_reserved`` below zero;
      - ``fulfil_order`` consumes reserved stock and writes the sale outflow.
    """

    async def reserve_stock(
        self,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        qty: Decimal,
        tenant_id: uuid.UUID,
        *,
        ref_type: str = "sale_order",
        ref_id: str,
    ) -> StockLevel: ...

    async def release_reservation(
        self,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        qty: Decimal,
        tenant_id: uuid.UUID,
        *,
        ref_type: str = "sale_order",
        ref_id: str,
    ) -> StockLevel: ...

    async def fulfil_order(
        self,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        qty: Decimal,
        tenant_id: uuid.UUID,
        *,
        ref_type: str = "sale_order",
        ref_id: str,
    ) -> StockLevel: ...


class InventoryServicePort(Protocol):
    """Business contract for the inventory service (router + CRM consumers)."""

    # --- Products / warehouses ---
    async def create_product(
        self, tenant_id: uuid.UUID, *, sku: str, name: str, **kwargs: object
    ) -> Product: ...

    async def create_warehouse(
        self, tenant_id: uuid.UUID, *, name: str, **kwargs: object
    ) -> Warehouse: ...

    # --- Stock operations ---
    async def adjust_stock(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        qty: Decimal,
        reason: str,
        ref_id: str,
    ) -> StockMovement: ...

    async def transfer_stock(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID,
        from_warehouse_id: uuid.UUID,
        to_warehouse_id: uuid.UUID,
        qty: Decimal,
        ref_id: str,
    ) -> tuple[StockMovement, StockMovement]: ...

    # --- Stock-health analytics (INV-ANL-001) ---
    async def dead_stock(
        self,
        tenant_id: uuid.UUID,
        *,
        days: int = 90,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[DeadStockItem]: ...

    async def count_dead_stock(self, tenant_id: uuid.UUID, *, days: int = 90) -> int: ...

    async def slow_movers(
        self,
        tenant_id: uuid.UUID,
        *,
        window_days: int = 180,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[SlowMoverItem]: ...

    async def count_slow_movers(self, tenant_id: uuid.UUID, *, window_days: int = 180) -> int: ...

    async def movement_trends(
        self,
        tenant_id: uuid.UUID,
        *,
        warehouse_id: uuid.UUID | None = None,
        weeks: int = 13,
    ) -> Sequence[MovementTrendPoint]: ...

    async def health_summary(
        self, tenant_id: uuid.UUID, *, days: int = 90
    ) -> StockHealthSummary: ...
