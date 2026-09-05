/**
 * Inventory API client (products, warehouses, stock, movements, alerts).
 *
 * All calls go through the same-origin /api/v1/* BFF proxy, which derives the
 * tenant slug from the Host header and forwards the in-memory access token (see
 * lib/api/http.ts). List endpoints use page/page_size and return the
 * ListResponse envelope ({ data, meta }); mutations are idempotent per
 * (ref_type, ref_id, warehouse) and require erp.inventory.* permissions
 * enforced server-side. Adjustments whose |qty| exceeds the approval threshold
 * require erp.inventory.adjust.approve - mirroring the core service default.
 */

import { apiDelete, apiFetch, apiFetchEnvelope, apiPatch, apiPost } from "@/lib/api/http";
import { getTenantSlug } from "@/lib/auth/session-store";

/** Mirrors CORE_INVENTORY_ADJUST_APPROVE_THRESHOLD (core settings default). */
export const ADJUST_APPROVE_THRESHOLD = 100;

export interface PaginationMeta {
    total: number;
    page: number;
    pageSize: number;
    totalPages: number;
}

export interface ListResponse<T> {
    data: T[];
    meta: PaginationMeta;
}

/** Money serialized as (amount-as-string, currency), e.g. ["12.50", "USD"]. */
export type Money = [string, string];

export interface Product {
    id: string;
    sku: string;
    name: string;
    category: string | null;
    unit: string | null;
    costPrice: Money;
    sellPrice: Money;
    reorderPoint: string;
    isActive: boolean;
    createdAt: string;
    updatedAt: string;
}

export interface Warehouse {
    id: string;
    name: string;
    location: string | null;
    isActive: boolean;
    createdAt: string;
    updatedAt: string;
}

export interface StockLevel {
    id: string;
    productId: string;
    warehouseId: string;
    qtyOnHand: string;
    qtyReserved: string;
    updatedAt: string;
}

export type MovementType =
    "receipt" | "issue" | "transfer" | "adjustment" | "reservation" | "release";

export interface StockMovement {
    id: string;
    productId: string;
    warehouseId: string;
    movementType: string;
    qty: string;
    refType: string;
    refId: string;
    createdAt: string;
}

export interface Transfer {
    fromMovement: StockMovement;
    toMovement: StockMovement;
}

export interface Alert {
    productId: string;
    warehouseId: string;
    sku: string;
    name: string;
    qtyOnHand: string;
    reorderPoint: string;
}

export interface CreateProductInput {
    sku: string;
    name: string;
    category?: string | null;
    unit?: string | null;
    costPrice?: number;
    sellPrice?: number;
    reorderPoint?: number;
}

export interface UpdateProductInput {
    sku?: string;
    name?: string;
    category?: string | null;
    unit?: string | null;
    costPrice?: number;
    sellPrice?: number;
    reorderPoint?: number;
}

export interface CreateWarehouseInput {
    name: string;
    location?: string | null;
}

export interface UpdateWarehouseInput {
    name?: string;
    location?: string | null;
}

export interface AdjustStockInput {
    productId: string;
    warehouseId: string;
    /** Signed delta - positive receives, negative issues. Must be non-zero. */
    qty: number;
    reason: string;
    refId?: string;
}

export interface TransferStockInput {
    productId: string;
    fromWarehouseId: string;
    toWarehouseId: string;
    qty: number;
    refId?: string;
}

export interface ReserveStockInput {
    productId: string;
    warehouseId: string;
    qty: number;
    refId?: string;
}

export interface ReleaseStockInput {
    productId: string;
    warehouseId: string;
    qty: number;
    refId?: string;
}

// ---------------------------------------------------------------------------
// Payload shapes (snake_case, as served by the backend)
// ---------------------------------------------------------------------------

interface MetaPayload {
    total?: unknown;
    page?: unknown;
    page_size?: unknown;
    total_pages?: unknown;
}

interface ListPayload {
    data?: unknown;
    meta?: unknown;
}

interface ProductPayload {
    id?: unknown;
    sku?: unknown;
    name?: unknown;
    category?: unknown;
    unit?: unknown;
    cost_price?: unknown;
    sell_price?: unknown;
    reorder_point?: unknown;
    is_active?: unknown;
    created_at?: unknown;
    updated_at?: unknown;
}

interface WarehousePayload {
    id?: unknown;
    name?: unknown;
    location?: unknown;
    is_active?: unknown;
    created_at?: unknown;
    updated_at?: unknown;
}

interface StockLevelPayload {
    id?: unknown;
    product_id?: unknown;
    warehouse_id?: unknown;
    qty_on_hand?: unknown;
    qty_reserved?: unknown;
    updated_at?: unknown;
}

interface StockMovementPayload {
    id?: unknown;
    product_id?: unknown;
    warehouse_id?: unknown;
    movement_type?: unknown;
    qty?: unknown;
    ref_type?: unknown;
    ref_id?: unknown;
    created_at?: unknown;
}

interface TransferPayload {
    from_movement?: unknown;
    to_movement?: unknown;
}

interface AlertPayload {
    product_id?: unknown;
    warehouse_id?: unknown;
    sku?: unknown;
    name?: unknown;
    qty_on_hand?: unknown;
    reorder_point?: unknown;
}

// ---------------------------------------------------------------------------
// Mappers
// ---------------------------------------------------------------------------

function toMoney(value: unknown): Money {
    if (Array.isArray(value) && value.length >= 2) {
        return [String(value[0] ?? "0"), String(value[1] ?? "USD")];
    }
    return ["0", "USD"];
}

function mapProduct(raw: ProductPayload): Product {
    return {
        id: String(raw.id ?? ""),
        sku: String(raw.sku ?? ""),
        name: String(raw.name ?? ""),
        category:
            typeof raw.category === "string" && raw.category
                ? raw.category
                : null,
        unit: typeof raw.unit === "string" && raw.unit ? raw.unit : null,
        costPrice: toMoney(raw.cost_price),
        sellPrice: toMoney(raw.sell_price),
        reorderPoint: String(raw.reorder_point ?? "0"),
        isActive: raw.is_active !== false,
        createdAt: String(raw.created_at ?? ""),
        updatedAt: String(raw.updated_at ?? ""),
    };
}

function mapWarehouse(raw: WarehousePayload): Warehouse {
    return {
        id: String(raw.id ?? ""),
        name: String(raw.name ?? ""),
        location:
            typeof raw.location === "string" && raw.location
                ? raw.location
                : null,
        isActive: raw.is_active !== false,
        createdAt: String(raw.created_at ?? ""),
        updatedAt: String(raw.updated_at ?? ""),
    };
}

function mapStockLevel(raw: StockLevelPayload): StockLevel {
    return {
        id: String(raw.id ?? ""),
        productId: String(raw.product_id ?? ""),
        warehouseId: String(raw.warehouse_id ?? ""),
        qtyOnHand: String(raw.qty_on_hand ?? "0"),
        qtyReserved: String(raw.qty_reserved ?? "0"),
        updatedAt: String(raw.updated_at ?? ""),
    };
}

function mapStockMovement(raw: StockMovementPayload): StockMovement {
    return {
        id: String(raw.id ?? ""),
        productId: String(raw.product_id ?? ""),
        warehouseId: String(raw.warehouse_id ?? ""),
        movementType: String(raw.movement_type ?? ""),
        qty: String(raw.qty ?? "0"),
        refType: String(raw.ref_type ?? ""),
        refId: String(raw.ref_id ?? ""),
        createdAt: String(raw.created_at ?? ""),
    };
}

function mapTransfer(raw: TransferPayload): Transfer {
    return {
        fromMovement: mapStockMovement(
            (raw.from_movement ?? {}) as StockMovementPayload,
        ),
        toMovement: mapStockMovement(
            (raw.to_movement ?? {}) as StockMovementPayload,
        ),
    };
}

function mapAlert(raw: AlertPayload): Alert {
    return {
        productId: String(raw.product_id ?? ""),
        warehouseId: String(raw.warehouse_id ?? ""),
        sku: String(raw.sku ?? ""),
        name: String(raw.name ?? ""),
        qtyOnHand: String(raw.qty_on_hand ?? "0"),
        reorderPoint: String(raw.reorder_point ?? "0"),
    };
}

function mapMeta(raw: MetaPayload | undefined | null): PaginationMeta {
    return {
        total: Number(raw?.total ?? 0),
        page: Number(raw?.page ?? 1),
        pageSize: Number(raw?.page_size ?? 0),
        totalPages: Number(raw?.total_pages ?? 0),
    };
}

function mapList<T, R>(
    raw: ListPayload | null | undefined,
    mapper: (item: T) => R,
): ListResponse<R> {
    const items = Array.isArray(raw?.data) ? raw.data.map(mapper) : [];
    return { data: items, meta: mapMeta(raw?.meta as MetaPayload | undefined) };
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function buildListParams(
    options: { page?: number; pageSize?: number },
    extra?: Record<string, string | undefined>,
): string {
    const params = new URLSearchParams();
    params.set("page", String(options.page ?? 1));
    params.set("page_size", String(options.pageSize ?? 20));
    if (extra) {
        for (const [key, value] of Object.entries(extra)) {
            if (value) params.set(key, value);
        }
    }
    return params.toString();
}

function newRefId(): string {
    if (
        typeof crypto !== "undefined" &&
        typeof crypto.randomUUID === "function"
    ) {
        return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Paginate through every page of a list loader, returning all items. */
export async function listAllPages<T>(
    loader: (page: number) => Promise<ListResponse<T>>,
): Promise<T[]> {
    const first = await loader(1);
    if (first.meta.totalPages <= 1) return first.data;
    const rest = await Promise.all(
        Array.from({ length: first.meta.totalPages - 1 }, (_, index) =>
            loader(index + 2),
        ),
    );
    return [...first.data, ...rest.flatMap((result) => result.data)];
}

// ---------------------------------------------------------------------------
// Cached catalogs
// ---------------------------------------------------------------------------

interface CatalogSnapshot<T> {
    tenant: string;
    fetchedAt: number;
    items: T[];
}

/**
 * Stock/movement/alert lists only carry ids, so the UI joins product and
 * warehouse display names client-side. Fetching the full catalog on every page
 * or filter change fired dozens of parallel requests per interaction, so it is
 * cached here per tenant for a short TTL and refreshed on demand via
 * `invalidateCatalog` (called after product/warehouse mutations).
 */
const CATALOG_TTL_MS = 5 * 60 * 1000;

let productsSnapshot: CatalogSnapshot<Product> | null = null;
let warehousesSnapshot: CatalogSnapshot<Warehouse> | null = null;
let productsRequest: Promise<Product[]> | null = null;
let warehousesRequest: Promise<Warehouse[]> | null = null;

async function loadAllProducts(): Promise<Product[]> {
    return listAllPages((page) =>
        listProducts({ page, pageSize: 100, includeInactive: true }),
    );
}

async function loadAllWarehouses(): Promise<Warehouse[]> {
    return listAllPages((page) =>
        listWarehouses({ page, pageSize: 100, includeInactive: true }),
    );
}

/** Read the full (active + archived) product catalog, cached per tenant. */
export async function getCatalogProducts(): Promise<Product[]> {
    const tenant = getTenantSlug();
    const cached = productsSnapshot;
    if (
        cached &&
        cached.tenant === tenant &&
        Date.now() - cached.fetchedAt < CATALOG_TTL_MS
    ) {
        return cached.items;
    }
    if (!productsRequest) {
        productsRequest = loadAllProducts()
            .then((items) => {
                productsSnapshot = { tenant, fetchedAt: Date.now(), items };
                return items;
            })
            .finally(() => {
                productsRequest = null;
            });
    }
    return productsRequest;
}

/** Read the full (active + archived) warehouse catalog, cached per tenant. */
export async function getCatalogWarehouses(): Promise<Warehouse[]> {
    const tenant = getTenantSlug();
    const cached = warehousesSnapshot;
    if (
        cached &&
        cached.tenant === tenant &&
        Date.now() - cached.fetchedAt < CATALOG_TTL_MS
    ) {
        return cached.items;
    }
    if (!warehousesRequest) {
        warehousesRequest = loadAllWarehouses()
            .then((items) => {
                warehousesSnapshot = {
                    tenant,
                    fetchedAt: Date.now(),
                    items,
                };
                return items;
            })
            .finally(() => {
                warehousesRequest = null;
            });
    }
    return warehousesRequest;
}

/** Drop both cached catalogs so the next read refetches (after mutations). */
export function invalidateCatalog(): void {
    productsSnapshot = null;
    warehousesSnapshot = null;
    productsRequest = null;
    warehousesRequest = null;
}

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------

export async function listProducts(
    options: {
        page?: number;
        pageSize?: number;
        category?: string;
        includeInactive?: boolean;
    } = {},
    fetchOptions: RequestInit = {},
): Promise<ListResponse<Product>> {
    const query = buildListParams(options, {
        category: options.category,
        include_inactive: options.includeInactive ? "true" : undefined,
    });
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/inventory/products?${query}`,
        fetchOptions,
    );
    return mapList(raw, mapProduct);
}

export async function createProduct(
    input: CreateProductInput,
): Promise<Product> {
    const raw = await apiPost<ProductPayload | null>(
        "/api/v1/inventory/products",
        {
            sku: input.sku,
            name: input.name,
            category: input.category || null,
            unit: input.unit || null,
            cost_price: [input.costPrice ?? 0, "USD"],
            sell_price: [input.sellPrice ?? 0, "USD"],
            reorder_point: input.reorderPoint ?? 0,
        },
    );
    return mapProduct(raw ?? {});
}

export async function updateProduct(
    id: string,
    input: UpdateProductInput,
): Promise<Product> {
    const raw = await apiPatch<ProductPayload | null>(
        `/api/v1/inventory/products/${id}`,
        {
            sku: input.sku,
            name: input.name,
            category: input.category ?? null,
            unit: input.unit ?? null,
            cost_price: [input.costPrice ?? 0, "USD"],
            sell_price: [input.sellPrice ?? 0, "USD"],
            reorder_point: input.reorderPoint ?? 0,
        },
    );
    return mapProduct(raw ?? {});
}

export async function deleteProduct(id: string): Promise<Product> {
    const raw = await apiDelete<ProductPayload | null>(
        `/api/v1/inventory/products/${id}`,
    );
    return mapProduct(raw ?? {});
}

export async function reactivateProduct(id: string): Promise<Product> {
    const raw = await apiPost<ProductPayload | null>(
        `/api/v1/inventory/products/${id}/reactivate`,
        {},
    );
    return mapProduct(raw ?? {});
}

// ---------------------------------------------------------------------------
// Warehouses
// ---------------------------------------------------------------------------

export async function listWarehouses(
    options: {
        page?: number;
        pageSize?: number;
        includeInactive?: boolean;
    } = {},
    fetchOptions: RequestInit = {},
): Promise<ListResponse<Warehouse>> {
    const query = buildListParams(options, {
        include_inactive: options.includeInactive ? "true" : undefined,
    });
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/inventory/warehouses?${query}`,
        fetchOptions,
    );
    return mapList(raw, mapWarehouse);
}

export async function createWarehouse(
    input: CreateWarehouseInput,
): Promise<Warehouse> {
    const raw = await apiPost<WarehousePayload | null>(
        "/api/v1/inventory/warehouses",
        {
            name: input.name,
            location: input.location || null,
        },
    );
    return mapWarehouse(raw ?? {});
}

export async function updateWarehouse(
    id: string,
    input: UpdateWarehouseInput,
): Promise<Warehouse> {
    const raw = await apiPatch<WarehousePayload | null>(
        `/api/v1/inventory/warehouses/${id}`,
        {
            name: input.name,
            location: input.location ?? null,
        },
    );
    return mapWarehouse(raw ?? {});
}

export async function deleteWarehouse(id: string): Promise<Warehouse> {
    const raw = await apiDelete<WarehousePayload | null>(
        `/api/v1/inventory/warehouses/${id}`,
    );
    return mapWarehouse(raw ?? {});
}

export async function reactivateWarehouse(id: string): Promise<Warehouse> {
    const raw = await apiPost<WarehousePayload | null>(
        `/api/v1/inventory/warehouses/${id}/reactivate`,
        {},
    );
    return mapWarehouse(raw ?? {});
}

// ---------------------------------------------------------------------------
// Stock
// ---------------------------------------------------------------------------

export async function listStockLevels(
    options: {
        page?: number;
        pageSize?: number;
        productId?: string;
        warehouseId?: string;
    } = {},
    fetchOptions: RequestInit = {},
): Promise<ListResponse<StockLevel>> {
    const query = buildListParams(options, {
        product_id: options.productId,
        warehouse_id: options.warehouseId,
    });
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/inventory/stock?${query}`,
        fetchOptions,
    );
    return mapList(raw, mapStockLevel);
}

export async function adjustStock(
    input: AdjustStockInput,
): Promise<StockMovement> {
    const raw = await apiPost<StockMovementPayload | null>(
        "/api/v1/inventory/stock/adjustments",
        {
            product_id: input.productId,
            warehouse_id: input.warehouseId,
            qty: input.qty,
            reason: input.reason,
            ref_id: input.refId ?? newRefId(),
        },
    );
    return mapStockMovement(raw ?? {});
}

export async function transferStock(
    input: TransferStockInput,
): Promise<Transfer> {
    const raw = await apiPost<TransferPayload | null>(
        "/api/v1/inventory/stock/transfers",
        {
            product_id: input.productId,
            from_warehouse_id: input.fromWarehouseId,
            to_warehouse_id: input.toWarehouseId,
            qty: input.qty,
            ref_id: input.refId ?? newRefId(),
        },
    );
    return mapTransfer(raw ?? {});
}

export async function reserveStock(
    input: ReserveStockInput,
): Promise<StockLevel> {
    const raw = await apiPost<StockLevelPayload | null>(
        "/api/v1/inventory/stock/reservations",
        {
            product_id: input.productId,
            warehouse_id: input.warehouseId,
            qty: input.qty,
            ref_id: input.refId ?? newRefId(),
        },
    );
    return mapStockLevel(raw ?? {});
}

export async function releaseStock(
    input: ReleaseStockInput,
): Promise<StockLevel> {
    const raw = await apiPost<StockLevelPayload | null>(
        "/api/v1/inventory/stock/releases",
        {
            product_id: input.productId,
            warehouse_id: input.warehouseId,
            qty: input.qty,
            ref_id: input.refId ?? newRefId(),
        },
    );
    return mapStockLevel(raw ?? {});
}

export async function listMovements(
    options: {
        page?: number;
        pageSize?: number;
        productId?: string;
        warehouseId?: string;
        movementType?: string;
    } = {},
    fetchOptions: RequestInit = {},
): Promise<ListResponse<StockMovement>> {
    const query = buildListParams(options, {
        product_id: options.productId,
        warehouse_id: options.warehouseId,
        movement_type: options.movementType,
    });
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/inventory/stock/movements?${query}`,
        fetchOptions,
    );
    return mapList(raw, mapStockMovement);
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export async function listAlerts(
    options: {
        page?: number;
        pageSize?: number;
    } = {},
    fetchOptions: RequestInit = {},
): Promise<ListResponse<Alert>> {
    const query = buildListParams(options);
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/inventory/alerts?${query}`,
        fetchOptions,
    );
    return mapList(raw, mapAlert);
}

// ---------------------------------------------------------------------------
// Stock-health analytics (INV-ANL-001)
// ---------------------------------------------------------------------------

export interface DeadStockItem {
    productId: string;
    sku: string;
    name: string;
    qtyOnHand: string;
    warehouseId: string | null;
    costPrice: Money | null;
    tiedUpValue: Money | null;
    lastOutboundAt: string | null;
}

export interface SlowMoverItem {
    productId: string;
    sku: string;
    name: string;
    qtyOnHand: string;
    turnoverRatio: string;
    warehouseId: string | null;
    costPrice: Money | null;
    carryingCost: Money | null;
    lastOutboundAt: string | null;
    suggestMarkdown: boolean;
}

export interface MovementTrendPoint {
    periodStart: string;
    warehouseId: string | null;
    receipts: string;
    issues: string;
    adjustments: string;
}

export interface StockHealthSummary {
    totalSkuCount: number;
    lowStockCount: number;
    deadStockCount: number;
    slowMoverCount: number;
    tiedUpCapital: Money | null;
}

interface DeadStockItemPayload {
    product_id?: unknown;
    sku?: unknown;
    name?: unknown;
    qty_on_hand?: unknown;
    warehouse_id?: unknown;
    cost_price?: unknown;
    tied_up_value?: unknown;
    last_outbound_at?: unknown;
}

interface SlowMoverItemPayload {
    product_id?: unknown;
    sku?: unknown;
    name?: unknown;
    qty_on_hand?: unknown;
    turnover_ratio?: unknown;
    warehouse_id?: unknown;
    cost_price?: unknown;
    carrying_cost?: unknown;
    last_outbound_at?: unknown;
    suggest_markdown?: unknown;
}

interface MovementTrendPointPayload {
    period_start?: unknown;
    warehouse_id?: unknown;
    receipts?: unknown;
    issues?: unknown;
    adjustments?: unknown;
}

interface StockHealthSummaryPayload {
    total_sku_count?: unknown;
    low_stock_count?: unknown;
    dead_stock_count?: unknown;
    slow_mover_count?: unknown;
    tied_up_capital?: unknown;
}

function toNullableMoney(value: unknown): Money | null {
    return Array.isArray(value) && value.length >= 2
        ? [String(value[0] ?? "0"), String(value[1] ?? "USD")]
        : null;
}

function mapDeadStockItem(raw: DeadStockItemPayload): DeadStockItem {
    return {
        productId: String(raw.product_id ?? ""),
        sku: String(raw.sku ?? ""),
        name: String(raw.name ?? ""),
        qtyOnHand: String(raw.qty_on_hand ?? "0"),
        warehouseId:
            typeof raw.warehouse_id === "string" && raw.warehouse_id
                ? raw.warehouse_id
                : null,
        costPrice: toNullableMoney(raw.cost_price),
        tiedUpValue: toNullableMoney(raw.tied_up_value),
        lastOutboundAt:
            typeof raw.last_outbound_at === "string" && raw.last_outbound_at
                ? raw.last_outbound_at
                : null,
    };
}

function mapSlowMoverItem(raw: SlowMoverItemPayload): SlowMoverItem {
    return {
        productId: String(raw.product_id ?? ""),
        sku: String(raw.sku ?? ""),
        name: String(raw.name ?? ""),
        qtyOnHand: String(raw.qty_on_hand ?? "0"),
        turnoverRatio: String(raw.turnover_ratio ?? "0"),
        warehouseId:
            typeof raw.warehouse_id === "string" && raw.warehouse_id
                ? raw.warehouse_id
                : null,
        costPrice: toNullableMoney(raw.cost_price),
        carryingCost: toNullableMoney(raw.carrying_cost),
        lastOutboundAt:
            typeof raw.last_outbound_at === "string" && raw.last_outbound_at
                ? raw.last_outbound_at
                : null,
        suggestMarkdown: raw.suggest_markdown === true,
    };
}

function mapMovementTrendPoint(raw: MovementTrendPointPayload): MovementTrendPoint {
    return {
        periodStart: String(raw.period_start ?? ""),
        warehouseId:
            typeof raw.warehouse_id === "string" && raw.warehouse_id
                ? raw.warehouse_id
                : null,
        receipts: String(raw.receipts ?? "0"),
        issues: String(raw.issues ?? "0"),
        adjustments: String(raw.adjustments ?? "0"),
    };
}

function mapStockHealthSummary(raw: StockHealthSummaryPayload): StockHealthSummary {
    return {
        totalSkuCount: Number(raw.total_sku_count ?? 0),
        lowStockCount: Number(raw.low_stock_count ?? 0),
        deadStockCount: Number(raw.dead_stock_count ?? 0),
        slowMoverCount: Number(raw.slow_mover_count ?? 0),
        tiedUpCapital: toNullableMoney(raw.tied_up_capital),
    };
}

/** Products with stock on hand but no outbound movement in the trailing days. */
export async function listDeadStock(
    options: { days?: number; page?: number; pageSize?: number } = {},
): Promise<ListResponse<DeadStockItem>> {
    const query = buildListParams(
        { page: options.page, pageSize: options.pageSize },
        { days: options.days !== undefined ? String(options.days) : undefined },
    );
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/inventory/health/dead-stock?${query}`,
        {},
    );
    return mapList(raw, (item) =>
        mapDeadStockItem(item as DeadStockItemPayload),
    );
}

/** Bottom-quartile turnover items with a suggested-markdown advice flag. */
export async function listSlowMovers(
    options: { windowDays?: number; page?: number; pageSize?: number } = {},
): Promise<ListResponse<SlowMoverItem>> {
    const query = buildListParams(
        { page: options.page, pageSize: options.pageSize },
        {
            window_days:
                options.windowDays !== undefined
                    ? String(options.windowDays)
                    : undefined,
        },
    );
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/inventory/health/slow-movers?${query}`,
        {},
    );
    return mapList(raw, (item) =>
        mapSlowMoverItem(item as SlowMoverItemPayload),
    );
}

/** Stacked weekly receipts/issues/adjustments for the trailing weeks. */
export async function listMovementTrends(
    options: { weeks?: number; warehouseId?: string } = {},
): Promise<ListResponse<MovementTrendPoint>> {
    const query = buildListParams({}, {
        weeks: options.weeks !== undefined ? String(options.weeks) : undefined,
        warehouse_id: options.warehouseId,
    });
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/inventory/health/trends?${query}`,
        {},
    );
    return mapList(raw, (point) =>
        mapMovementTrendPoint(point as MovementTrendPointPayload),
    );
}

/** Aggregate stock-health metrics (also feeds the SKY-63 narrator digest). */
export async function getStockHealthSummary(
    options: { days?: number } = {},
): Promise<StockHealthSummary> {
    const query = buildListParams({}, {
        days: options.days !== undefined ? String(options.days) : undefined,
    });
    const raw = await apiFetch<StockHealthSummaryPayload>(
        `/api/v1/inventory/health/summary?${query}`,
        {},
    );
    return mapStockHealthSummary(raw ?? {});
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const MOVEMENT_TYPE_LABELS: Record<string, string> = {
    receipt: "Receipt",
    issue: "Issue",
    transfer: "Transfer",
    adjustment: "Adjustment",
    reservation: "Reservation",
    release: "Release",
};

/** Format a (amount, currency) money tuple for display. */
export function formatMoney(value: Money | null | undefined): string {
    if (!value) return "-";
    const [amount, currency] = value;
    if (currency === "USD") return `$${amount}`;
    return `${amount} ${currency}`;
}

/** Short, locale-aware date for ledger/audit timestamps. */
export function formatDate(value: string | null | undefined): string {
    if (!value) return "-";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "-";
    return parsed.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

/** Human-readable label for a stock movement type. */
export function movementTypeLabel(value: string): string {
    return (
        MOVEMENT_TYPE_LABELS[value] ??
        value.charAt(0).toUpperCase() + value.slice(1)
    );
}
