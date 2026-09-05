"""Inventory repository - DB operations for products, warehouses, stock, movements.

Stock is the ledger: ``add_movement`` appends an immutable movement row and then
recomputes the materialized ``erp_stock_levels`` row from the ledger in the SAME
transaction. The level's CHECK constraints (``qty_on_hand >= 0`` and
``0 <= qty_reserved <= qty_on_hand``) are evaluated by the database when the
materialized row is written, so an oversell or over-reservation fails the whole
transaction - including the movement insert - independent of service logic.

All probes are tenant-scoped: lookups take an explicit ``tenant_id`` and every
session is additionally bound by RLS (``app.current_tenant_id``), so a tenant
can never read or write another tenant's rows at either layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Select, and_, case, func, or_, select, update
from sqlalchemy.engine import CursorResult

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
from core.features.inventory.models.product import ErpProductModel
from core.features.inventory.models.stock_level import ErpStockLevelModel
from core.features.inventory.models.stock_movement import ErpStockMovementModel
from core.features.inventory.models.warehouse import ErpWarehouseModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Movements that feed qty_reserved (and are EXCLUDED from qty_on_hand).
_RESERVATION_TYPES = (StockMovementType.RESERVATION, StockMovementType.RELEASE)

# Outbound movements that count against turnover for the stock-health analytics
# (INV-ANL-001): every ISSUE leaves the warehouse.
_OUTBOUND_TYPES = (StockMovementType.ISSUE,)

# Sentinel distinguishing "field not in the PATCH body" from "clear to null".
_UNSET: object = object()


# (product, current on-hand, window outbound qty, window last outbound) row.
Slot = tuple[Product, Decimal, Decimal, datetime]


@dataclass(frozen=True)
class _RankedSlowMover:
    """Slow-mover candidate with its computed turnover ratio."""

    product: Product
    qty_on_hand: Decimal
    out_qty: Decimal
    last_outbound_at: datetime | None
    turnover_ratio: Decimal


def _product_to_orm(product: Product) -> ErpProductModel:
    kwargs: dict[str, object] = {
        "tenant_id": product.tenant_id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "unit": product.unit,
        "cost_price": product.cost_price.amount,
        "cost_currency_code": product.cost_price.currency,
        "sell_price": product.sell_price.amount,
        "sell_currency_code": product.sell_price.currency,
        "reorder_point": product.reorder_point,
        "is_active": product.is_active,
    }
    if product.id is not None:
        kwargs["id"] = product.id
    return ErpProductModel(**kwargs)


def _product_from_orm(model: ErpProductModel) -> Product:
    return Product(
        id=model.id,
        tenant_id=model.tenant_id,
        sku=model.sku,
        name=model.name,
        category=model.category,
        unit=model.unit,
        cost_price=Money(model.cost_price, model.cost_currency_code),
        sell_price=Money(model.sell_price, model.sell_currency_code),
        reorder_point=model.reorder_point,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _warehouse_to_orm(warehouse: Warehouse) -> ErpWarehouseModel:
    kwargs: dict[str, object] = {
        "tenant_id": warehouse.tenant_id,
        "name": warehouse.name,
        "location": warehouse.location,
        "is_active": warehouse.is_active,
    }
    if warehouse.id is not None:
        kwargs["id"] = warehouse.id
    return ErpWarehouseModel(**kwargs)


def _warehouse_from_orm(model: ErpWarehouseModel) -> Warehouse:
    return Warehouse(
        id=model.id,
        tenant_id=model.tenant_id,
        name=model.name,
        location=model.location,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _stock_level_from_orm(model: ErpStockLevelModel) -> StockLevel:
    return StockLevel(
        id=model.id,
        tenant_id=model.tenant_id,
        product_id=model.product_id,
        warehouse_id=model.warehouse_id,
        qty_on_hand=model.qty_on_hand,
        qty_reserved=model.qty_reserved,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _stock_movement_from_orm(model: ErpStockMovementModel) -> StockMovement:
    return StockMovement(
        id=model.id,
        tenant_id=model.tenant_id,
        product_id=model.product_id,
        warehouse_id=model.warehouse_id,
        movement_type=model.movement_type,
        qty=model.qty,
        ref_type=model.ref_type,
        ref_id=model.ref_id,
        created_at=model.created_at,
    )


class InventoryRepository:
    """Concrete SQLAlchemy implementation of :class:`InventoryRepositoryPort`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    async def create_product(self, product: Product) -> Product:
        model = _product_to_orm(product)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _product_from_orm(model)

    async def get_product(self, product_id: uuid.UUID, tenant_id: uuid.UUID) -> Product | None:
        stmt = select(ErpProductModel).where(
            ErpProductModel.tenant_id == tenant_id,
            ErpProductModel.id == product_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _product_from_orm(model) if model is not None else None

    async def get_product_by_sku(self, sku: str, tenant_id: uuid.UUID) -> Product | None:
        stmt = select(ErpProductModel).where(
            ErpProductModel.tenant_id == tenant_id,
            ErpProductModel.sku == sku,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _product_from_orm(model) if model is not None else None

    async def deactivate_product(
        self, product_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Product | None:
        stmt = select(ErpProductModel).where(
            ErpProductModel.tenant_id == tenant_id,
            ErpProductModel.id == product_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        model.is_active = False
        await self.session.flush()
        await self.session.refresh(model)
        return _product_from_orm(model)

    async def reactivate_product(
        self, product_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Product | None:
        stmt = select(ErpProductModel).where(
            ErpProductModel.tenant_id == tenant_id,
            ErpProductModel.id == product_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        model.is_active = True
        await self.session.flush()
        await self.session.refresh(model)
        return _product_from_orm(model)

    async def update_product(
        self,
        product_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        sku: str | object = _UNSET,
        name: str | object = _UNSET,
        category: str | object | None = _UNSET,
        unit: str | object | None = _UNSET,
        cost_price: Money | object = _UNSET,
        sell_price: Money | object = _UNSET,
        reorder_point: Decimal | object = _UNSET,
    ) -> Product | None:
        stmt = select(ErpProductModel).where(
            ErpProductModel.tenant_id == tenant_id,
            ErpProductModel.id == product_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        if sku is not _UNSET:
            model.sku = cast("str", sku)
        if name is not _UNSET:
            model.name = cast("str", name)
        if category is not _UNSET:
            model.category = cast("str | None", category)
        if unit is not _UNSET:
            model.unit = cast("str | None", unit)
        if cost_price is not _UNSET:
            model.cost_price = cast("Money", cost_price).amount
            model.cost_currency_code = cast("Money", cost_price).currency
        if sell_price is not _UNSET:
            model.sell_price = cast("Money", sell_price).amount
            model.sell_currency_code = cast("Money", sell_price).currency
        if reorder_point is not _UNSET:
            model.reorder_point = cast("Decimal", reorder_point)
        await self.session.flush()
        await self.session.refresh(model)
        return _product_from_orm(model)

    async def list_products(
        self,
        tenant_id: uuid.UUID,
        *,
        include_inactive: bool = False,
        category: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[Product]:
        stmt = select(ErpProductModel).where(ErpProductModel.tenant_id == tenant_id)
        if not include_inactive:
            stmt = stmt.where(ErpProductModel.is_active.is_(True))
        if category:
            stmt = stmt.where(ErpProductModel.category == category)
        stmt = stmt.order_by(ErpProductModel.sku).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return [_product_from_orm(model) for model in result.scalars().all()]

    async def count_products(
        self,
        tenant_id: uuid.UUID,
        *,
        include_inactive: bool = False,
        category: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ErpProductModel)
            .where(ErpProductModel.tenant_id == tenant_id)
        )
        if not include_inactive:
            stmt = stmt.where(ErpProductModel.is_active.is_(True))
        if category:
            stmt = stmt.where(ErpProductModel.category == category)
        return int((await self.session.execute(stmt)).scalar_one())

    # ------------------------------------------------------------------
    # Warehouses
    # ------------------------------------------------------------------

    async def create_warehouse(self, warehouse: Warehouse) -> Warehouse:
        model = _warehouse_to_orm(warehouse)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _warehouse_from_orm(model)

    async def get_warehouse(
        self, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Warehouse | None:
        stmt = select(ErpWarehouseModel).where(
            ErpWarehouseModel.tenant_id == tenant_id,
            ErpWarehouseModel.id == warehouse_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _warehouse_from_orm(model) if model is not None else None

    async def deactivate_warehouse(
        self, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Warehouse | None:
        stmt = select(ErpWarehouseModel).where(
            ErpWarehouseModel.tenant_id == tenant_id,
            ErpWarehouseModel.id == warehouse_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        model.is_active = False
        await self.session.flush()
        await self.session.refresh(model)
        return _warehouse_from_orm(model)

    async def reactivate_warehouse(
        self, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Warehouse | None:
        stmt = select(ErpWarehouseModel).where(
            ErpWarehouseModel.tenant_id == tenant_id,
            ErpWarehouseModel.id == warehouse_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        model.is_active = True
        await self.session.flush()
        await self.session.refresh(model)
        return _warehouse_from_orm(model)

    async def update_warehouse(
        self,
        warehouse_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        name: str | object = _UNSET,
        location: str | object | None = _UNSET,
    ) -> Warehouse | None:
        stmt = select(ErpWarehouseModel).where(
            ErpWarehouseModel.tenant_id == tenant_id,
            ErpWarehouseModel.id == warehouse_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        if name is not _UNSET:
            model.name = cast("str", name)
        if location is not _UNSET:
            model.location = cast("str | None", location)
        await self.session.flush()
        await self.session.refresh(model)
        return _warehouse_from_orm(model)

    async def list_warehouses(
        self,
        tenant_id: uuid.UUID,
        *,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[Warehouse]:
        stmt = select(ErpWarehouseModel).where(ErpWarehouseModel.tenant_id == tenant_id)
        if not include_inactive:
            stmt = stmt.where(ErpWarehouseModel.is_active.is_(True))
        stmt = stmt.order_by(ErpWarehouseModel.name).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return [_warehouse_from_orm(model) for model in result.scalars().all()]

    async def count_warehouses(
        self, tenant_id: uuid.UUID, *, include_inactive: bool = False
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ErpWarehouseModel)
            .where(ErpWarehouseModel.tenant_id == tenant_id)
        )
        if not include_inactive:
            stmt = stmt.where(ErpWarehouseModel.is_active.is_(True))
        return int((await self.session.execute(stmt)).scalar_one())

    # ------------------------------------------------------------------
    # Stock levels
    # ------------------------------------------------------------------

    async def get_stock_level(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> StockLevel | None:
        stmt = select(ErpStockLevelModel).where(
            ErpStockLevelModel.tenant_id == tenant_id,
            ErpStockLevelModel.product_id == product_id,
            ErpStockLevelModel.warehouse_id == warehouse_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _stock_level_from_orm(model) if model is not None else None

    async def recompute_stock_level(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> StockLevel:
        """Rebuild the materialized level from the ledger for one product/warehouse.

        ``qty_on_hand`` = sum of all non-reservation movements; ``qty_reserved``
        = net of reservation/release movements. Writing the result runs the
        table's CHECK constraints, so over-reservation / negative stock raises
        here and rolls back the enclosing transaction.
        """
        reservation_types = tuple(_RESERVATION_TYPES)
        on_hand_expr = func.coalesce(
            func.sum(
                case(
                    (
                        ~ErpStockMovementModel.movement_type.in_(reservation_types),
                        ErpStockMovementModel.qty,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        reserved_expr = func.coalesce(
            func.sum(
                case(
                    (
                        ErpStockMovementModel.movement_type.in_(reservation_types),
                        ErpStockMovementModel.qty,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        stmt = select(on_hand_expr.label("on_hand"), reserved_expr.label("reserved")).where(
            ErpStockMovementModel.tenant_id == tenant_id,
            ErpStockMovementModel.product_id == product_id,
            ErpStockMovementModel.warehouse_id == warehouse_id,
        )
        row = (await self.session.execute(stmt)).one()
        qty_on_hand = Decimal(row.on_hand)
        qty_reserved = Decimal(row.reserved)

        stmt = select(ErpStockLevelModel).where(
            ErpStockLevelModel.tenant_id == tenant_id,
            ErpStockLevelModel.product_id == product_id,
            ErpStockLevelModel.warehouse_id == warehouse_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()

        if model is None:
            model = ErpStockLevelModel(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                qty_on_hand=qty_on_hand,
                qty_reserved=qty_reserved,
            )
            self.session.add(model)
        else:
            model.qty_on_hand = qty_on_hand
            model.qty_reserved = qty_reserved

        await self.session.flush()
        await self.session.refresh(model)
        return _stock_level_from_orm(model)

    async def list_stock_levels(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[StockLevel]:
        stmt = select(ErpStockLevelModel).where(ErpStockLevelModel.tenant_id == tenant_id)
        if product_id is not None:
            stmt = stmt.where(ErpStockLevelModel.product_id == product_id)
        if warehouse_id is not None:
            stmt = stmt.where(ErpStockLevelModel.warehouse_id == warehouse_id)
        stmt = (
            stmt.order_by(ErpStockLevelModel.product_id, ErpStockLevelModel.warehouse_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [_stock_level_from_orm(model) for model in result.scalars().all()]

    async def count_stock_levels(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ErpStockLevelModel)
            .where(ErpStockLevelModel.tenant_id == tenant_id)
        )
        if product_id is not None:
            stmt = stmt.where(ErpStockLevelModel.product_id == product_id)
        if warehouse_id is not None:
            stmt = stmt.where(ErpStockLevelModel.warehouse_id == warehouse_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def sum_stock_by_product(
        self, product_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> tuple[Decimal, Decimal]:
        """Total on-hand / reserved quantity for a product across warehouses."""
        stmt = select(
            func.coalesce(func.sum(ErpStockLevelModel.qty_on_hand), 0).label("on_hand"),
            func.coalesce(func.sum(ErpStockLevelModel.qty_reserved), 0).label("reserved"),
        ).where(
            ErpStockLevelModel.tenant_id == tenant_id,
            ErpStockLevelModel.product_id == product_id,
        )
        row = (await self.session.execute(stmt)).one()
        return Decimal(row.on_hand), Decimal(row.reserved)

    async def sum_stock_by_warehouse(
        self, warehouse_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> tuple[Decimal, Decimal]:
        """Total on-hand / reserved quantity for a warehouse across products."""
        stmt = select(
            func.coalesce(func.sum(ErpStockLevelModel.qty_on_hand), 0).label("on_hand"),
            func.coalesce(func.sum(ErpStockLevelModel.qty_reserved), 0).label("reserved"),
        ).where(
            ErpStockLevelModel.tenant_id == tenant_id,
            ErpStockLevelModel.warehouse_id == warehouse_id,
        )
        row = (await self.session.execute(stmt)).one()
        return Decimal(row.on_hand), Decimal(row.reserved)

    async def list_low_stock(
        self,
        tenant_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[tuple[StockLevel, Product]]:
        """Levels currently at or below their product's reorder point."""
        stmt = (
            select(ErpStockLevelModel, ErpProductModel)
            .join(
                ErpProductModel,
                and_(
                    ErpProductModel.tenant_id == ErpStockLevelModel.tenant_id,
                    ErpProductModel.id == ErpStockLevelModel.product_id,
                ),
            )
            .where(
                ErpStockLevelModel.tenant_id == tenant_id,
                ErpProductModel.is_active.is_(True),
                ErpStockLevelModel.qty_on_hand <= ErpProductModel.reorder_point,
            )
            .order_by(ErpStockLevelModel.qty_on_hand.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            (_stock_level_from_orm(level), _product_from_orm(product))
            for level, product in result.all()
        ]

    async def count_low_stock(self, tenant_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(ErpStockLevelModel)
            .join(
                ErpProductModel,
                and_(
                    ErpProductModel.tenant_id == ErpStockLevelModel.tenant_id,
                    ErpProductModel.id == ErpStockLevelModel.product_id,
                ),
            )
            .where(
                ErpStockLevelModel.tenant_id == tenant_id,
                ErpProductModel.is_active.is_(True),
                ErpStockLevelModel.qty_on_hand <= ErpProductModel.reorder_point,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    # ------------------------------------------------------------------
    # Guarded reservation updates (atomic row-lock + CHECK fallback)
    #
    # Reservation mutations run a conditional UPDATE on the materialized
    # level FIRST: the ``WHERE`` re-evaluates against the freshly locked row,
    # so concurrent reserve/release calls serialize on the row lock and the
    # invariant ``qty_reserved <= qty_on_hand`` is enforced before any ledger
    # row is written. The ledger movement is then appended and the level
    # recomputed, keeping the projection consistent with the ledger. The DB
    # CHECK constraint remains the final defense if the guard is bypassed.
    # ------------------------------------------------------------------

    async def apply_reservation_qty(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, qty: Decimal, tenant_id: uuid.UUID
    ) -> bool:
        """Atomically add ``qty`` to qty_reserved iff the result stays <= qty_on_hand."""
        stmt = (
            update(ErpStockLevelModel)
            .where(
                ErpStockLevelModel.tenant_id == tenant_id,
                ErpStockLevelModel.product_id == product_id,
                ErpStockLevelModel.warehouse_id == warehouse_id,
                ErpStockLevelModel.qty_reserved + qty <= ErpStockLevelModel.qty_on_hand,
            )
            .values(qty_reserved=ErpStockLevelModel.qty_reserved + qty)
        )
        result = cast("CursorResult[Any]", await self.session.execute(stmt))
        return result.rowcount > 0

    async def apply_release_qty(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, qty: Decimal, tenant_id: uuid.UUID
    ) -> bool:
        """Atomically subtract ``qty`` from qty_reserved iff the result stays >= 0."""
        stmt = (
            update(ErpStockLevelModel)
            .where(
                ErpStockLevelModel.tenant_id == tenant_id,
                ErpStockLevelModel.product_id == product_id,
                ErpStockLevelModel.warehouse_id == warehouse_id,
                ErpStockLevelModel.qty_reserved - qty >= 0,
            )
            .values(qty_reserved=ErpStockLevelModel.qty_reserved - qty)
        )
        result = cast("CursorResult[Any]", await self.session.execute(stmt))
        return result.rowcount > 0

    async def apply_consume_qty(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, qty: Decimal, tenant_id: uuid.UUID
    ) -> bool:
        """Atomically release ``qty`` from qty_reserved (fulfilment step)."""
        return await self.apply_release_qty(product_id, warehouse_id, qty, tenant_id)

    # ------------------------------------------------------------------
    # Movements (immutable - no update, no delete)
    # ------------------------------------------------------------------

    async def add_movement(self, movement: StockMovement) -> StockMovement:
        """Insert an immutable ledger row and recompute the level atomically.

        Idempotent per ``(tenant_id, ref_type, ref_id, warehouse_id)``: if the
        ref was already applied to this warehouse, the existing movement is
        returned instead of a duplicate insert.
        """
        existing = await self.get_movement_by_ref(
            movement.ref_type,
            movement.ref_id,
            movement.warehouse_id,
            movement.tenant_id,
        )
        if existing is not None:
            return existing

        model = ErpStockMovementModel(
            tenant_id=movement.tenant_id,
            product_id=movement.product_id,
            warehouse_id=movement.warehouse_id,
            movement_type=movement.movement_type,
            qty=movement.qty,
            ref_type=movement.ref_type,
            ref_id=movement.ref_id,
        )
        if movement.id is not None:
            model.id = movement.id
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)

        await self.recompute_stock_level(
            movement.product_id, movement.warehouse_id, movement.tenant_id
        )
        return _stock_movement_from_orm(model)

    async def get_movement_by_ref(
        self,
        ref_type: str,
        ref_id: str,
        warehouse_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> StockMovement | None:
        stmt = select(ErpStockMovementModel).where(
            ErpStockMovementModel.tenant_id == tenant_id,
            ErpStockMovementModel.ref_type == ref_type,
            ErpStockMovementModel.ref_id == ref_id,
            ErpStockMovementModel.warehouse_id == warehouse_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _stock_movement_from_orm(model) if model is not None else None

    async def list_movements(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        movement_type: StockMovementType | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[StockMovement]:
        stmt = select(ErpStockMovementModel).where(ErpStockMovementModel.tenant_id == tenant_id)
        if product_id is not None:
            stmt = stmt.where(ErpStockMovementModel.product_id == product_id)
        if warehouse_id is not None:
            stmt = stmt.where(ErpStockMovementModel.warehouse_id == warehouse_id)
        if movement_type is not None:
            stmt = stmt.where(ErpStockMovementModel.movement_type == movement_type)
        stmt = stmt.order_by(ErpStockMovementModel.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return [_stock_movement_from_orm(model) for model in result.scalars().all()]

    async def count_movements(
        self,
        tenant_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        movement_type: StockMovementType | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ErpStockMovementModel)
            .where(ErpStockMovementModel.tenant_id == tenant_id)
        )
        if product_id is not None:
            stmt = stmt.where(ErpStockMovementModel.product_id == product_id)
        if warehouse_id is not None:
            stmt = stmt.where(ErpStockMovementModel.warehouse_id == warehouse_id)
        if movement_type is not None:
            stmt = stmt.where(ErpStockMovementModel.movement_type == movement_type)
        return int((await self.session.execute(stmt)).scalar_one())

    # ------------------------------------------------------------------
    # Stock-health analytics (INV-ANL-001) — read-only, tenant-scoped.
    #
    # All queries are indexed for the analytics access path by migration 0037
    # (ix_erp_stock_movements_tenant_wh_type_created) and filter on tenant_id
    # first so RLS + index agree. Valuations are computed at cost_price on the
    # SERVER only; the router gates the money fields behind erp.inventory.cost.
    # ------------------------------------------------------------------

    def _dead_stock_stmt(
        self,
        tenant_id: uuid.UUID,
        *,
        days: int,
        as_counts: bool = False,
    ) -> Select[Any]:
        """Shared dead-stock query: active products with on-hand stock but no
        outbound (ISSUE) movement inside the trailing ``days`` window."""
        cutoff = datetime.now(UTC) - timedelta(days=days)

        on_hand = (
            select(
                ErpStockLevelModel.product_id,
                func.sum(ErpStockLevelModel.qty_on_hand).label("qty_on_hand"),
            )
            .where(ErpStockLevelModel.tenant_id == tenant_id)
            .group_by(ErpStockLevelModel.product_id)
            .subquery()
        )
        last_out = (
            select(
                ErpStockMovementModel.product_id,
                func.max(ErpStockMovementModel.created_at).label("last_out"),
            )
            .where(
                ErpStockMovementModel.tenant_id == tenant_id,
                ErpStockMovementModel.movement_type.in_(_OUTBOUND_TYPES),
            )
            .group_by(ErpStockMovementModel.product_id)
            .subquery()
        )
        where = (
            ErpProductModel.tenant_id == tenant_id,
            ErpProductModel.is_active.is_(True),
            on_hand.c.qty_on_hand > 0,
            or_(last_out.c.last_out.is_(None), last_out.c.last_out < cutoff),
        )
        if as_counts:
            return (
                select(func.count())
                .select_from(ErpProductModel)
                .join(on_hand, ErpProductModel.id == on_hand.c.product_id)
                .outerjoin(last_out, ErpProductModel.id == last_out.c.product_id)
                .where(*where)
            )
        return (
            select(
                ErpProductModel,
                on_hand.c.qty_on_hand,
                last_out.c.last_out,
            )
            .join(on_hand, ErpProductModel.id == on_hand.c.product_id)
            .outerjoin(last_out, ErpProductModel.id == last_out.c.product_id)
            .where(*where)
            .order_by(on_hand.c.qty_on_hand.desc())
        )

    async def dead_stock(
        self,
        tenant_id: uuid.UUID,
        *,
        days: int = 90,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[DeadStockItem]:
        stmt = self._dead_stock_stmt(tenant_id, days=days, as_counts=False)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        items: list[DeadStockItem] = []
        for product, qty_on_hand, last_out in result.all():
            product_ent = _product_from_orm(product)
            cost = product_ent.cost_price
            items.append(
                DeadStockItem(
                    tenant_id=tenant_id,
                    product_id=cast("uuid.UUID", product_ent.id),
                    sku=product_ent.sku,
                    name=product_ent.name,
                    qty_on_hand=Decimal(qty_on_hand),
                    cost_price=cost,
                    tied_up_value=Money(Decimal(qty_on_hand) * cost.amount, cost.currency),
                    last_outbound_at=last_out,
                )
            )
        return items

    async def count_dead_stock(self, tenant_id: uuid.UUID, *, days: int = 90) -> int:
        stmt = self._dead_stock_stmt(tenant_id, days=days, as_counts=True)
        return int((await self.session.execute(stmt)).scalar_one())

    async def _slow_mover_rows(self, tenant_id: uuid.UUID, *, window_days: int) -> list[Slot]:
        """Eligible (on-hand > 0, active) products with trailing outbound data.

        Returns tuples of (product, qty_on_hand, outbound_qty, last_outbound).
        """
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        on_hand = (
            select(
                ErpStockLevelModel.product_id,
                func.sum(ErpStockLevelModel.qty_on_hand).label("qty_on_hand"),
            )
            .where(ErpStockLevelModel.tenant_id == tenant_id)
            .group_by(ErpStockLevelModel.product_id)
            .subquery()
        )
        outbound = (
            select(
                ErpStockMovementModel.product_id,
                func.sum(func.abs(ErpStockMovementModel.qty)).label("out_qty"),
                func.max(ErpStockMovementModel.created_at).label("last_out"),
            )
            .where(
                ErpStockMovementModel.tenant_id == tenant_id,
                ErpStockMovementModel.movement_type.in_(_OUTBOUND_TYPES),
                ErpStockMovementModel.created_at >= cutoff,
            )
            .group_by(ErpStockMovementModel.product_id)
            .subquery()
        )
        stmt = (
            select(ErpProductModel, on_hand.c.qty_on_hand, outbound.c.out_qty, outbound.c.last_out)
            .join(on_hand, ErpProductModel.id == on_hand.c.product_id)
            .outerjoin(outbound, ErpProductModel.id == outbound.c.product_id)
            .where(
                ErpProductModel.tenant_id == tenant_id,
                ErpProductModel.is_active.is_(True),
                on_hand.c.qty_on_hand > 0,
            )
        )
        result = await self.session.execute(stmt)
        rows: list[Slot] = []
        for product, qty_on_hand, out_qty, last_out in result.all():
            product_ent = _product_from_orm(product)
            rows.append(
                (
                    product_ent,
                    Decimal(qty_on_hand),
                    Decimal(out_qty) if out_qty is not None else Decimal("0"),
                    last_out,
                )
            )
        return rows

    def _rank_slow_movers(self, rows: Sequence[Slot]) -> list[_RankedSlowMover]:
        ranked: list[_RankedSlowMover] = []
        for product, on_hand, out_qty, last_out in rows:
            base = on_hand if on_hand >= Decimal("1") else Decimal("1")
            ranked.append(
                _RankedSlowMover(
                    product=product,
                    qty_on_hand=on_hand,
                    out_qty=out_qty,
                    last_outbound_at=last_out,
                    turnover_ratio=out_qty / base,
                )
            )
        return ranked

    @staticmethod
    def _slow_mover_cutoff(ranked: Sequence[_RankedSlowMover]) -> Decimal:
        """Median turnover ratio — items at/below it are the slow movers."""
        if not ranked:
            return Decimal("0")
        ratios = sorted(r.turnover_ratio for r in ranked)
        n = len(ratios)
        mid = n // 2
        if n % 2 == 1:
            return ratios[mid]
        return (ratios[mid - 1] + ratios[mid]) / Decimal("2")

    async def slow_movers(
        self,
        tenant_id: uuid.UUID,
        *,
        window_days: int = 180,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[SlowMoverItem]:
        rows = await self._slow_mover_rows(tenant_id, window_days=window_days)
        ranked = self._rank_slow_movers(rows)
        cutoff = self._slow_mover_cutoff(ranked)
        matched = [r for r in ranked if Decimal("0") < r.turnover_ratio <= cutoff]
        page = matched[offset : offset + limit]
        items: list[SlowMoverItem] = []
        for r in page:
            product = r.product
            cost = product.cost_price
            items.append(
                SlowMoverItem(
                    tenant_id=tenant_id,
                    product_id=cast("uuid.UUID", product.id),
                    sku=product.sku,
                    name=product.name,
                    qty_on_hand=r.qty_on_hand,
                    turnover_ratio=r.turnover_ratio,
                    cost_price=cost,
                    carrying_cost=Money(
                        r.qty_on_hand * cost.amount * Decimal("0.25"), cost.currency
                    ),
                    last_outbound_at=r.last_outbound_at,
                    suggest_markdown=bool(r.turnover_ratio < Decimal("0.5")),
                )
            )
        return items

    async def count_slow_movers(self, tenant_id: uuid.UUID, *, window_days: int = 180) -> int:
        rows = await self._slow_mover_rows(tenant_id, window_days=window_days)
        ranked = self._rank_slow_movers(rows)
        cutoff = self._slow_mover_cutoff(ranked)
        return sum(1 for r in ranked if Decimal("0") < r.turnover_ratio <= cutoff)

    async def movement_trends(
        self,
        tenant_id: uuid.UUID,
        *,
        warehouse_id: uuid.UUID | None = None,
        weeks: int = 13,
    ) -> Sequence[MovementTrendPoint]:
        cutoff = datetime.now(UTC) - timedelta(weeks=weeks)
        period = func.date_trunc("week", ErpStockMovementModel.created_at)
        stmt = (
            select(
                period.label("period"),
                ErpStockMovementModel.warehouse_id,
                ErpStockMovementModel.movement_type,
                func.sum(ErpStockMovementModel.qty).label("qty"),
            )
            .where(
                ErpStockMovementModel.tenant_id == tenant_id,
                ErpStockMovementModel.created_at >= cutoff,
            )
            .group_by(
                period, ErpStockMovementModel.warehouse_id, ErpStockMovementModel.movement_type
            )
            .order_by(period)
        )
        if warehouse_id is not None:
            stmt = stmt.where(ErpStockMovementModel.warehouse_id == warehouse_id)
        result = await self.session.execute(stmt)
        by_week: dict[tuple[datetime, uuid.UUID | None], MovementTrendPoint] = {}
        for row in result.all():
            key = (row.period, row.warehouse_id)
            point = by_week.get(key)
            if point is None:
                point = MovementTrendPoint(
                    tenant_id=tenant_id,
                    period_start=row.period,
                    warehouse_id=row.warehouse_id,
                )
                by_week[key] = point
            qty = Decimal(row.qty)
            if row.movement_type == StockMovementType.RECEIPT:
                point = MovementTrendPoint(
                    tenant_id=point.tenant_id,
                    period_start=point.period_start,
                    warehouse_id=point.warehouse_id,
                    receipts=qty,
                    issues=point.issues,
                    adjustments=point.adjustments,
                )
            elif row.movement_type == StockMovementType.ISSUE:
                point = MovementTrendPoint(
                    tenant_id=point.tenant_id,
                    period_start=point.period_start,
                    warehouse_id=point.warehouse_id,
                    receipts=point.receipts,
                    issues=abs(qty),
                    adjustments=point.adjustments,
                )
            elif row.movement_type == StockMovementType.ADJUSTMENT:
                point = MovementTrendPoint(
                    tenant_id=point.tenant_id,
                    period_start=point.period_start,
                    warehouse_id=point.warehouse_id,
                    receipts=point.receipts,
                    issues=point.issues,
                    adjustments=qty,
                )
            by_week[key] = point
        return list(by_week.values())

    async def health_summary(self, tenant_id: uuid.UUID, *, days: int = 90) -> StockHealthSummary:
        stmt = self._dead_stock_stmt(tenant_id, days=days, as_counts=False)
        result = await self.session.execute(stmt)
        dead_count = 0
        tied_up = Decimal("0")
        currency = "USD"
        seen_currency = False
        for product, qty_on_hand, _ in result.all():
            product_ent = _product_from_orm(product)
            cost = product_ent.cost_price
            if not seen_currency:
                currency = cost.currency
                seen_currency = True
            dead_count += 1
            tied_up += Decimal(qty_on_hand) * cost.amount
        slow_count = await self.count_slow_movers(tenant_id)
        low_count = await self.count_low_stock(tenant_id)
        total_sku = await self.count_products(tenant_id)
        return StockHealthSummary(
            tenant_id=tenant_id,
            total_sku_count=total_sku,
            low_stock_count=low_count,
            dead_stock_count=dead_count,
            slow_mover_count=slow_count,
            tied_up_capital=Money(tied_up, currency),
        )

    async def commit(self) -> None:
        """Commit the current transaction - services own the transaction lifecycle."""
        await self.session.commit()
