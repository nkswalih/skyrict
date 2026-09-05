import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getStockHealthSummary,
  listAlerts,
  listDeadStock,
  listMovementTrends,
  listMovements,
  listProducts,
  listSlowMovers,
  listStockLevels,
  listWarehouses,
} from "@/lib/api/inventory-api";
import type { apiFetchEnvelope } from "@/lib/api/http";

const httpMock = vi.fn<typeof apiFetchEnvelope>();

type Envelope = { data?: unknown; meta?: unknown };

/**
 * Simulate the real http helpers: `apiFetchEnvelope` returns the whole
 * envelope, while `apiFetch`/`apiPost`/... unwrap `payload.data`. This mirrors
 * lib/api/http.ts so a regression back to `apiFetch` for a list endpoint
 * (which hands mapList the bare array) is caught by the tests.
 */
vi.mock("@/lib/api/http", () => ({
  apiFetch: async (_path: string, _options?: RequestInit) => {
    const result = await httpMock(_path, _options);
    return (result as Envelope).data;
  },
  apiFetchEnvelope: (_path: string, _options?: RequestInit) =>
    httpMock(_path, _options),
  apiPost: async (_path: string) => {
    const result = await httpMock(_path, { method: "POST" });
    return (result as Envelope).data;
  },
  apiPatch: async (_path: string) => {
    const result = await httpMock(_path, { method: "PATCH" });
    return (result as Envelope).data;
  },
  apiDelete: async (_path: string) => {
    const result = await httpMock(_path, { method: "DELETE" });
    return (result as Envelope).data;
  },
}));

describe("inventory list endpoints", () => {
  beforeEach(() => {
    httpMock.mockReset();
  });

  it("maps the products envelope into products with pagination", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          id: "p-1",
          sku: "SKU-1001",
          name: "Steel bracket",
          category: "Hardware",
          unit: "pcs",
          cost_price: ["2.5000", "USD"],
          sell_price: ["8.9900", "USD"],
          reorder_point: "25.0000",
          is_active: true,
          created_at: "2026-07-01T10:00:00Z",
          updated_at: "2026-07-01T10:00:00Z",
        },
      ],
      meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });

    const result = await listProducts({ page: 1, pageSize: 20 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/products?page=1&page_size=20",
      {},
    );
    expect(result.meta).toEqual({
      total: 1,
      page: 1,
      pageSize: 20,
      totalPages: 1,
    });
    expect(result.data).toHaveLength(1);
    expect(result.data[0]).toMatchObject({
      id: "p-1",
      sku: "SKU-1001",
      name: "Steel bracket",
      category: "Hardware",
      unit: "pcs",
      costPrice: ["2.5000", "USD"],
      sellPrice: ["8.9900", "USD"],
      reorderPoint: "25.0000",
      isActive: true,
    });
  });

  it("returns an empty list for an empty envelope", async () => {
    httpMock.mockResolvedValue({
      data: [],
      meta: { total: 0, page: 1, page_size: 20, total_pages: 0 },
    });

    const result = await listProducts();

    expect(result.data).toEqual([]);
    expect(result.meta.totalPages).toBe(0);
  });

  it("maps the warehouses envelope", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          id: "w-1",
          name: "Main DC",
          location: "Riyadh",
          is_active: true,
          created_at: "2026-07-01T10:00:00Z",
          updated_at: "2026-07-01T10:00:00Z",
        },
      ],
      meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });

    const result = await listWarehouses({ page: 1, pageSize: 20 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/warehouses?page=1&page_size=20",
      {},
    );
    expect(result.data[0]).toMatchObject({ name: "Main DC" });
  });

  it("maps the stock levels envelope", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          id: "s-1",
          product_id: "p-1",
          warehouse_id: "w-1",
          qty_on_hand: "12.0000",
          qty_reserved: "0.0000",
          updated_at: "2026-07-01T10:00:00Z",
        },
      ],
      meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });

    const result = await listStockLevels({ page: 1, pageSize: 20 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/stock?page=1&page_size=20",
      {},
    );
    expect(result.data[0]).toMatchObject({
      productId: "p-1",
      warehouseId: "w-1",
      qtyOnHand: "12.0000",
      qtyReserved: "0.0000",
    });
  });

  it("maps the movements envelope", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          id: "m-1",
          product_id: "p-1",
          warehouse_id: "w-1",
          movement_type: "receipt",
          qty: "5.0000",
          ref_type: "adjustment",
          ref_id: "r-1",
          created_at: "2026-07-01T10:00:00Z",
        },
      ],
      meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });

    const result = await listMovements({ page: 1, pageSize: 20 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/stock/movements?page=1&page_size=20",
      {},
    );
    expect(result.data[0]).toMatchObject({
      productId: "p-1",
      movementType: "receipt",
      qty: "5.0000",
    });
  });

  it("maps the alerts envelope", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          product_id: "p-1",
          warehouse_id: "w-1",
          sku: "SKU-1001",
          name: "Steel bracket",
          qty_on_hand: "4.0000",
          reorder_point: "25.0000",
        },
      ],
      meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });

    const result = await listAlerts({ page: 1, pageSize: 20 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/alerts?page=1&page_size=20",
      {},
    );
    expect(result.data[0]).toMatchObject({
      productId: "p-1",
      sku: "SKU-1001",
      qtyOnHand: "4.0000",
    });
  });
});

describe("stock-health endpoints", () => {
  beforeEach(() => {
    httpMock.mockReset();
  });

  it("maps the dead-stock envelope (cost fields preserved)", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          product_id: "p-1",
          sku: "SKU-1001",
          name: "Legacy widget",
          qty_on_hand: "40.0000",
          warehouse_id: "w-1",
          cost_price: ["3.00", "USD"],
          tied_up_value: ["120.00", "USD"],
          last_outbound_at: "2026-04-01T10:00:00Z",
        },
      ],
      meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });

    const result = await listDeadStock({ days: 90 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/health/dead-stock?page=1&page_size=20&days=90",
      {},
    );
    expect(result.data[0]).toMatchObject({
      productId: "p-1",
      sku: "SKU-1001",
      name: "Legacy widget",
      qtyOnHand: "40.0000",
      warehouseId: "w-1",
      costPrice: ["3.00", "USD"],
      tiedUpValue: ["120.00", "USD"],
    });
  });

  it("blanks dead-stock cost fields when the server omits them", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          product_id: "p-1",
          sku: "SKU-1001",
          name: "Legacy widget",
          qty_on_hand: "40.0000",
          warehouse_id: null,
          last_outbound_at: null,
        },
      ],
      meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });

    const result = await listDeadStock();

    expect(result.data[0]).toMatchObject({
      warehouseId: null,
      costPrice: null,
      tiedUpValue: null,
      lastOutboundAt: null,
    });
  });

  it("maps the slow-mover envelope with markdown flag", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          product_id: "p-2",
          sku: "SKU-1002",
          name: "Slow bracket",
          qty_on_hand: "18.0000",
          turnover_ratio: "0.1200",
          warehouse_id: "w-1",
          cost_price: ["2.00", "USD"],
          carrying_cost: ["0.60", "USD"],
          last_outbound_at: "2026-02-01T10:00:00Z",
          suggest_markdown: true,
        },
      ],
      meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });

    const result = await listSlowMovers({ windowDays: 180 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/health/slow-movers?page=1&page_size=20&window_days=180",
      {},
    );
    expect(result.data[0]).toMatchObject({
      productId: "p-2",
      sku: "SKU-1002",
      turnoverRatio: "0.1200",
      costPrice: ["2.00", "USD"],
      carryingCost: ["0.60", "USD"],
      suggestMarkdown: true,
    });
  });

  it("maps the movement-trends envelope", async () => {
    httpMock.mockResolvedValue({
      data: [
        {
          period_start: "2026-08-01T00:00:00Z",
          warehouse_id: "w-1",
          receipts: "12.0000",
          issues: "7.0000",
          adjustments: "1.0000",
        },
      ],
      meta: { total: 1, page: 1, page_size: 1, total_pages: 1 },
    });

    const result = await listMovementTrends({ weeks: 13 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/health/trends?page=1&page_size=20&weeks=13",
      {},
    );
    expect(result.data[0]).toMatchObject({
      periodStart: "2026-08-01T00:00:00Z",
      warehouseId: "w-1",
      receipts: "12.0000",
      issues: "7.0000",
      adjustments: "1.0000",
    });
  });

  it("maps the summary envelope and unwraps .data from apiFetch", async () => {
    httpMock.mockResolvedValue({
      data: {
        total_sku_count: 42,
        low_stock_count: 7,
        dead_stock_count: 3,
        slow_mover_count: 5,
        tied_up_capital: ["240.00", "USD"],
      },
      meta: null,
    });

    const result = await getStockHealthSummary({ days: 90 });

    expect(httpMock).toHaveBeenCalledWith(
      "/api/v1/inventory/health/summary?page=1&page_size=20&days=90",
      {},
    );
    expect(result).toEqual({
      totalSkuCount: 42,
      lowStockCount: 7,
      deadStockCount: 3,
      slowMoverCount: 5,
      tiedUpCapital: ["240.00", "USD"],
    });
  });

  it("returns null tied-up capital when the caller lacks cost access", async () => {
    httpMock.mockResolvedValue({
      data: {
        total_sku_count: 42,
        low_stock_count: 7,
        dead_stock_count: 3,
        slow_mover_count: 5,
        tied_up_capital: null,
      },
      meta: null,
    });

    const result = await getStockHealthSummary();

    expect(result.tiedUpCapital).toBeNull();
  });
});
