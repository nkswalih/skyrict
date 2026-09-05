"""Inventory HTTP router - thin marshalling, business rules live in the service.

Endpoints follow docs/modules/inventory-warehouse.md §8. Every route requires a
valid access JWT + tenant context (via shared deps) and a module-level
permission dependency resolved from DB grants at request time. Responses are
wrapped in ``ResponseEnvelope``; lists use offset/limit with ``PaginationMeta``.

Permissions (spec §7.3 / §8): read endpoints need ``erp.inventory.read``;
product/warehouse creation and transfers need ``erp.inventory.write``;
adjustments need ``erp.inventory.adjust`` plus above-threshold approval via
``erp.inventory.adjust.approve`` (enforced by the service against the threshold).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from core.api.deps import (
    get_adjustment_authority,
    get_inventory_service,
    get_tenant_context,
    require_ingest_m2m_or_permission,
    require_permission,
    resolve_permission,
)
from core.core.permissions import (
    ERP_INVENTORY_ADJUST,
    ERP_INVENTORY_COST,
    ERP_INVENTORY_READ,
    ERP_INVENTORY_WRITE,
)
from core.features.inventory.repository import _UNSET
from core.features.inventory.schemas import (
    AlertResponse,
    DeadStockItemResponse,
    MovementTrendPointResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    SlowMoverItemResponse,
    StockAdjustmentCreate,
    StockHealthSummaryResponse,
    StockLevelResponse,
    StockMovementResponse,
    StockReleaseCreate,
    StockReserveCreate,
    StockTransferCreate,
    TransferResponse,
    WarehouseCreate,
    WarehouseResponse,
    WarehouseUpdate,
    money_input,
)
from skyrict_common.pagination import PaginationParams
from skyrict_common.schemas import ListResponse, PaginationMeta, ResponseEnvelope

if TYPE_CHECKING:
    from core.features.inventory.service import InventoryService

router = APIRouter(prefix="/inventory", tags=["inventory"])

# Module-level permission dependency singletons (§7.3) so the factory runs once.
_require_inventory_read = require_permission(ERP_INVENTORY_READ)
_require_inventory_write = require_permission(ERP_INVENTORY_WRITE)
_require_inventory_adjust = require_permission(ERP_INVENTORY_ADJUST)
# Non-raising: true only when the caller holds the cost key (INV-ANL-001).
_resolve_inventory_cost = resolve_permission(ERP_INVENTORY_COST)
# The catalog list (reindex/ingest target) additionally accepts ai-agent's m2m
# ingest secret (CORE_AI_INGEST_TOKEN); every other route stays JWT-only.
_require_catalog_read = require_ingest_m2m_or_permission(ERP_INVENTORY_READ)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


@router.get("/products", response_model=ListResponse[ProductResponse])
async def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    _: dict[str, object] = Depends(_require_catalog_read),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ListResponse[ProductResponse]:
    """List products (active by default; ``?include_inactive=true`` for archived)."""
    params = PaginationParams.create(page, page_size)
    products = await service.list_products(
        tenant_id,
        include_inactive=include_inactive,
        category=category,
        offset=params.offset,
        limit=params.limit,
    )
    total = await service.count_products(
        tenant_id, include_inactive=include_inactive, category=category
    )
    return ListResponse(
        data=[ProductResponse.from_entity(p) for p in products],
        meta=PaginationMeta.create(total=total, page=params.page, page_size=params.page_size),
    )


@router.post("/products", response_model=ResponseEnvelope[ProductResponse])
async def create_product(
    body: ProductCreate,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[ProductResponse]:
    """Create a product (SKU must be unique within the tenant)."""
    product = await service.create_product(
        tenant_id,
        sku=body.sku,
        name=body.name,
        category=body.category,
        unit=body.unit,
        cost_price=money_input(body.cost_price),
        sell_price=money_input(body.sell_price),
        reorder_point=body.reorder_point,
    )
    return ResponseEnvelope(data=ProductResponse.from_entity(product), message="Product created")


@router.patch("/products/{product_id}", response_model=ResponseEnvelope[ProductResponse])
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[ProductResponse]:
    """Partially update a product (SKU stays unique within the tenant)."""
    updates = body.model_fields_set
    product = await service.update_product(
        tenant_id,
        product_id,
        sku=body.sku if "sku" in updates else _UNSET,
        name=body.name if "name" in updates else _UNSET,
        category=body.category if "category" in updates else _UNSET,
        unit=body.unit if "unit" in updates else _UNSET,
        cost_price=money_input(body.cost_price) if "cost_price" in updates else _UNSET,
        sell_price=money_input(body.sell_price) if "sell_price" in updates else _UNSET,
        reorder_point=body.reorder_point if "reorder_point" in updates else _UNSET,
    )
    return ResponseEnvelope(data=ProductResponse.from_entity(product), message="Product updated")


@router.delete("/products/{product_id}", response_model=ResponseEnvelope[ProductResponse])
async def delete_product(
    product_id: uuid.UUID,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[ProductResponse]:
    """Archive a product (is_active = false; ledger history is preserved).

    Blocked with 409 while reservations exist; on-hand quantity may remain and
    is written off via a stock adjustment. Un-archive with POST .../reactivate.
    """
    product = await service.deactivate_product(tenant_id, product_id)
    return ResponseEnvelope(data=ProductResponse.from_entity(product), message="Product deleted")


@router.post("/products/{product_id}/reactivate", response_model=ResponseEnvelope[ProductResponse])
async def reactivate_product(
    product_id: uuid.UUID,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[ProductResponse]:
    """Un-archive a product (is_active = true)."""
    product = await service.reactivate_product(tenant_id, product_id)
    return ResponseEnvelope(
        data=ProductResponse.from_entity(product), message="Product reactivated"
    )


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------


@router.get("/warehouses", response_model=ListResponse[WarehouseResponse])
async def list_warehouses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_inactive: bool = Query(default=False),
    _: dict[str, object] = Depends(_require_inventory_read),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ListResponse[WarehouseResponse]:
    """List warehouses (active by default; ``?include_inactive=true`` for archived)."""
    params = PaginationParams.create(page, page_size)
    warehouses = await service.list_warehouses(
        tenant_id, include_inactive=include_inactive, offset=params.offset, limit=params.limit
    )
    total = await service.count_warehouses(tenant_id, include_inactive=include_inactive)
    return ListResponse(
        data=[WarehouseResponse.from_entity(w) for w in warehouses],
        meta=PaginationMeta.create(total=total, page=params.page, page_size=params.page_size),
    )


@router.post("/warehouses", response_model=ResponseEnvelope[WarehouseResponse])
async def create_warehouse(
    body: WarehouseCreate,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[WarehouseResponse]:
    """Create a warehouse in the routed tenant."""
    warehouse = await service.create_warehouse(tenant_id, name=body.name, location=body.location)
    return ResponseEnvelope(
        data=WarehouseResponse.from_entity(warehouse), message="Warehouse created"
    )


@router.patch("/warehouses/{warehouse_id}", response_model=ResponseEnvelope[WarehouseResponse])
async def update_warehouse(
    warehouse_id: uuid.UUID,
    body: WarehouseUpdate,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[WarehouseResponse]:
    """Partially update a warehouse."""
    updates = body.model_fields_set
    warehouse = await service.update_warehouse(
        tenant_id,
        warehouse_id,
        name=body.name if "name" in updates else _UNSET,
        location=body.location if "location" in updates else _UNSET,
    )
    return ResponseEnvelope(
        data=WarehouseResponse.from_entity(warehouse), message="Warehouse updated"
    )


@router.delete("/warehouses/{warehouse_id}", response_model=ResponseEnvelope[WarehouseResponse])
async def delete_warehouse(
    warehouse_id: uuid.UUID,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[WarehouseResponse]:
    """Archive a warehouse (is_active = false; ledger history is preserved).

    Blocked with 409 while reservations exist; on-hand quantity may remain and
    is written off via a stock adjustment. Un-archive with POST .../reactivate.
    """
    warehouse = await service.deactivate_warehouse(tenant_id, warehouse_id)
    return ResponseEnvelope(
        data=WarehouseResponse.from_entity(warehouse), message="Warehouse deleted"
    )


@router.post(
    "/warehouses/{warehouse_id}/reactivate", response_model=ResponseEnvelope[WarehouseResponse]
)
async def reactivate_warehouse(
    warehouse_id: uuid.UUID,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[WarehouseResponse]:
    """Un-archive a warehouse (is_active = true)."""
    warehouse = await service.reactivate_warehouse(tenant_id, warehouse_id)
    return ResponseEnvelope(
        data=WarehouseResponse.from_entity(warehouse), message="Warehouse reactivated"
    )


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------


@router.get("/stock", response_model=ListResponse[StockLevelResponse])
async def list_stock_levels(
    product_id: str | None = Query(default=None),
    warehouse_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: dict[str, object] = Depends(_require_inventory_read),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ListResponse[StockLevelResponse]:
    """List current stock levels, optionally filtered by product/warehouse."""
    from uuid import UUID

    params = PaginationParams.create(page, page_size)
    pid = UUID(product_id) if product_id else None
    wid = UUID(warehouse_id) if warehouse_id else None
    levels = await service.list_stock_levels(
        tenant_id,
        product_id=pid,
        warehouse_id=wid,
        offset=params.offset,
        limit=params.limit,
    )
    total = await service.count_stock_levels(tenant_id, product_id=pid, warehouse_id=wid)
    return ListResponse(
        data=[StockLevelResponse.from_entity(level) for level in levels],
        meta=PaginationMeta.create(total=total, page=params.page, page_size=params.page_size),
    )


@router.post(
    "/stock/adjustments",
    response_model=ResponseEnvelope[StockMovementResponse],
    status_code=201,
)
async def adjust_stock(
    body: StockAdjustmentCreate,
    _: dict[str, object] = Depends(_require_inventory_adjust),
    approved: bool = Depends(get_adjustment_authority),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[StockMovementResponse]:
    """Record a signed stock adjustment (idempotent per ``ref_id`` + warehouse)."""
    movement = await service.adjust_stock(
        tenant_id,
        product_id=body.product_id,
        warehouse_id=body.warehouse_id,
        qty=body.qty,
        reason=body.reason,
        ref_id=body.ref_id,
        approved=approved,
    )
    return ResponseEnvelope(
        data=StockMovementResponse.from_entity(movement), message="Stock adjusted"
    )


@router.post(
    "/stock/transfers",
    response_model=ResponseEnvelope[TransferResponse],
    status_code=201,
)
async def transfer_stock(
    body: StockTransferCreate,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[TransferResponse]:
    """Move stock between two warehouses atomically (2 movements or none)."""
    out_movement, in_movement = await service.transfer_stock(
        tenant_id,
        product_id=body.product_id,
        from_warehouse_id=body.from_warehouse_id,
        to_warehouse_id=body.to_warehouse_id,
        qty=body.qty,
        ref_id=body.ref_id,
    )
    return ResponseEnvelope(
        data=TransferResponse.from_entities(out_movement, in_movement),
        message="Stock transferred",
    )


@router.post(
    "/stock/reservations",
    response_model=ResponseEnvelope[StockLevelResponse],
    status_code=201,
)
async def reserve_stock(
    body: StockReserveCreate,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[StockLevelResponse]:
    """Reserve stock for a pending order (qty_reserved increases)."""
    level = await service.reserve_stock(
        body.product_id,
        body.warehouse_id,
        body.qty,
        tenant_id,
        ref_id=body.ref_id,
    )
    return ResponseEnvelope(data=StockLevelResponse.from_entity(level), message="Stock reserved")


@router.post(
    "/stock/releases",
    response_model=ResponseEnvelope[StockLevelResponse],
    status_code=201,
)
async def release_reservation(
    body: StockReleaseCreate,
    _: dict[str, object] = Depends(_require_inventory_write),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[StockLevelResponse]:
    """Release previously reserved stock (qty_reserved decreases)."""
    level = await service.release_reservation(
        body.product_id,
        body.warehouse_id,
        body.qty,
        tenant_id,
        ref_id=body.ref_id,
    )
    return ResponseEnvelope(
        data=StockLevelResponse.from_entity(level), message="Reservation released"
    )


@router.get(
    "/stock/movements",
    response_model=ListResponse[StockMovementResponse],
)
async def list_movements(
    product_id: str | None = Query(default=None),
    warehouse_id: str | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: dict[str, object] = Depends(_require_inventory_read),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ListResponse[StockMovementResponse]:
    """List immutable ledger entries, newest first."""
    from uuid import UUID

    from core.domain.value_objects import StockMovementType

    params = PaginationParams.create(page, page_size)
    pid = UUID(product_id) if product_id else None
    wid = UUID(warehouse_id) if warehouse_id else None
    mtype = StockMovementType(movement_type) if movement_type else None
    movements = await service.list_movements(
        tenant_id,
        product_id=pid,
        warehouse_id=wid,
        movement_type=mtype,
        offset=params.offset,
        limit=params.limit,
    )
    total = await service.count_movements(
        tenant_id, product_id=pid, warehouse_id=wid, movement_type=mtype
    )
    return ListResponse(
        data=[StockMovementResponse.from_entity(m) for m in movements],
        meta=PaginationMeta.create(total=total, page=params.page, page_size=params.page_size),
    )


@router.get("/alerts", response_model=ListResponse[AlertResponse])
async def list_alerts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: dict[str, object] = Depends(_require_inventory_read),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ListResponse[AlertResponse]:
    """List products currently at or below their reorder point."""
    params = PaginationParams.create(page, page_size)
    alerts = await service.list_alerts(tenant_id, offset=params.offset, limit=params.limit)
    total = await service.count_alerts(tenant_id)
    return ListResponse(
        data=[AlertResponse.from_entities(level, product) for level, product in alerts],
        meta=PaginationMeta.create(total=total, page=params.page, page_size=params.page_size),
    )


# ---------------------------------------------------------------------------
# Stock-health analytics (INV-ANL-001)
# ---------------------------------------------------------------------------


@router.get(
    "/health/dead-stock",
    response_model=ListResponse[DeadStockItemResponse],
)
async def list_dead_stock(
    days: int = Query(default=90, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: dict[str, object] = Depends(_require_inventory_read),
    has_cost: bool = Depends(_resolve_inventory_cost),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ListResponse[DeadStockItemResponse]:
    """Products with stock on hand but no outbound in the trailing ``days``.

    Cost / tied-up-value figures are only populated when the caller holds
    ``erp.inventory.cost``; otherwise they are null (server-side gating).
    """
    params = PaginationParams.create(page, page_size)
    items = await service.dead_stock(tenant_id, days=days, offset=params.offset, limit=params.limit)
    total = await service.count_dead_stock(tenant_id, days=days)
    return ListResponse(
        data=[DeadStockItemResponse.from_entity(item, include_cost=has_cost) for item in items],
        meta=PaginationMeta.create(total=total, page=params.page, page_size=params.page_size),
    )


@router.get(
    "/health/slow-movers",
    response_model=ListResponse[SlowMoverItemResponse],
)
async def list_slow_movers(
    window_days: int = Query(default=180, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: dict[str, object] = Depends(_require_inventory_read),
    has_cost: bool = Depends(_resolve_inventory_cost),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ListResponse[SlowMoverItemResponse]:
    """Bottom-quartile turnover items with a suggested-markdown advice flag.

    ``suggest_markdown`` is advice only — it NEVER changes a price.
    """
    params = PaginationParams.create(page, page_size)
    items = await service.slow_movers(
        tenant_id,
        window_days=window_days,
        offset=params.offset,
        limit=params.limit,
    )
    total = await service.count_slow_movers(tenant_id, window_days=window_days)
    return ListResponse(
        data=[SlowMoverItemResponse.from_entity(item, include_cost=has_cost) for item in items],
        meta=PaginationMeta.create(total=total, page=params.page, page_size=params.page_size),
    )


@router.get(
    "/health/trends",
    response_model=ListResponse[MovementTrendPointResponse],
)
async def list_movement_trends(
    weeks: int = Query(default=13, ge=1, le=104),
    warehouse_id: str | None = Query(default=None),
    _: dict[str, object] = Depends(_require_inventory_read),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ListResponse[MovementTrendPointResponse]:
    """Stacked weekly receipts/issues/adjustments for the trailing ``weeks``."""
    from uuid import UUID

    wid = UUID(warehouse_id) if warehouse_id else None
    points = await service.movement_trends(tenant_id, warehouse_id=wid, weeks=weeks)
    return ListResponse(
        data=[MovementTrendPointResponse.from_entity(p) for p in points],
        meta=PaginationMeta.create(total=len(points), page=1, page_size=max(len(points), 1)),
    )


@router.get(
    "/health/summary",
    response_model=ResponseEnvelope[StockHealthSummaryResponse],
)
async def get_health_summary(
    days: int = Query(default=90, ge=1),
    _: dict[str, object] = Depends(_require_inventory_read),
    has_cost: bool = Depends(_resolve_inventory_cost),
    tenant_id: str = Depends(get_tenant_context),
    service: InventoryService = Depends(get_inventory_service),
) -> ResponseEnvelope[StockHealthSummaryResponse]:
    """Aggregate stock-health metrics (feeds the SKY-63 narrator digest)."""
    summary = await service.health_summary(tenant_id, days=days)
    return ResponseEnvelope(
        data=StockHealthSummaryResponse.from_entity(summary, include_cost=has_cost),
        message="Stock health summary",
    )
