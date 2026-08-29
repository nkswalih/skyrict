# M-INV — Inventory & Warehouse Module (Phase 1)

> **Status:** Draft — approved scope. Target: `services/core`, starter plan.
> **Owner:** Abhinav
> **Dependencies:** identity service (JWT verification, permissions, tenant context), `services/core` skeleton (M3), billing gating (SKY-32..36, enforced externally — does not block building the module).

This document is the complete, unambiguous specification for building the Inventory & Warehouse module. Follow sections in order; every task in the build checklist (§11) links back to the section that defines it.

---

## 1. Overview

The inventory module is the **operational truth for stock**: it tracks what products a company sells (`erp_products`), where they are stored (`erp_warehouses`), how much is currently on hand (`erp_stock_levels`), and every movement that changed the count (`erp_stock_movements`).

**The one idea to internalize: stock is a ledger, not a number.** You never "set the count to 50". You record a movement (`+50 received`) and the count is *derived* from the movements. This makes stock verifiable against money records.

**Consumers of this module (built in later phases):**
- **CRM (M-CRM):** order confirmation calls the reservation port (§5.4) to reserve stock.
- **Finance (M-FIN):** invoices reference fulfilled quantities.
- **Reporting (M-RPT):** "stock on hand vs reorder point", "movement by type", "slow movers" queries read this module's data.

---

## 2. Scope

### 2.1 In scope (Phase 1)
- Products and warehouses (CRUD)
- Stock levels (`qty_on_hand`, `qty_reserved`)
- Stock movements: `receive`, `adjust`, `transfer`, `sale`, `return`
- Reorder-point alerts (emit `inventory.stock.level_changed`)
- Reservation port for sales-order confirmation (called by CRM later)

### 2.2 Out of scope (Phase 1)
- Procurement / purchasing
- Production / manufacturing
- Pricing engine (cost/sell prices are recorded, not computed)
- Negative-stock sales (sales may not go below zero)
- Multi-warehouse routing / transfer approvals

---

## 3. Data model

Every table below carries the shared columns from the base mixins:

| Column | Type | Constraint |
|---|---|---|
| `id` | UUID | PK, default `uuid4` |
| `created_at` | timestamptz | NOT NULL, `server_default now()` |
| `updated_at` | timestamptz | NOT NULL, `server_default now()`, `onupdate now()` |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id` (opaque UUID), indexed, **RLS key** |

Table names use the `erp_` prefix. Reference tables (e.g. `erp_currencies`) are global, read-only, and have **no** `tenant_id` (see §6.5).

### 3.1 `erp_products` — what a company sells

| Column | Type / Constraint | Why it exists |
|---|---|---|
| `tenant_id` | UUID, NOT NULL, indexed | Ownership + RLS key |
| `sku` | String(64), NOT NULL | Product code. **Unique per tenant**: `UNIQUE (tenant_id, sku)` named `uq_erp_products_tenant_sku` |
| `name` | String(256), NOT NULL | Display name |
| `category` | String(128), nullable | Grouping for reporting/filtering |
| `unit` | String(32), NOT NULL | Unit of measure ("pcs", "kg") |
| `cost_price` | Numeric(18,4), NOT NULL default 0 | Money (§10.1) — landed cost |
| `sell_price` | Numeric(18,4), NOT NULL default 0 | Money (§10.1) — selling price |
| `reorder_point` | Integer, NOT NULL default 0 | Threshold that triggers the low-stock alert (§4.4) |
| `is_active` | Boolean, NOT NULL, default `true` | Soft-disable a product — never hard-delete (§10.6) |

### 3.2 `erp_warehouses` — where stock lives

| Column | Type / Constraint | Why it exists |
|---|---|---|
| `tenant_id` | UUID, NOT NULL, indexed | Ownership + RLS key |
| `name` | String(256), NOT NULL | Warehouse display name |
| `location` | String(256), nullable | Physical location |
| `is_active` | Boolean, NOT NULL, default `true` | Soft-disable a warehouse |

**Unique per tenant:** `UNIQUE (tenant_id, name)` named `uq_erp_warehouses_tenant_name`.

### 3.3 `erp_stock_levels` — the materialized current count

| Column | Type / Constraint | Why it exists |
|---|---|---|
| `tenant_id` | UUID, NOT NULL, indexed | Ownership + RLS key |
| `product_id` | UUID, NOT NULL | FK → `erp_products.id` (composite with tenant — §6.5) |
| `warehouse_id` | UUID, NOT NULL | FK → `erp_warehouses.id` (composite with tenant) |
| `qty_on_hand` | Integer, NOT NULL default 0 | Current derived total — recomputed on write (§4.1) |
| `qty_reserved` | Integer, NOT NULL default 0 | Reserved for confirmed-but-unfulfilled orders (§5.4) |

**Constraints:**
- `UNIQUE (tenant_id, product_id, warehouse_id)` named `uq_erp_stock_levels_product_warehouse`
- `CHECK (qty_on_hand >= 0)` named `ck_erp_stock_levels_qty_on_hand_non_negative`
- `CHECK (qty_reserved >= 0)` named `ck_erp_stock_levels_qty_reserved_non_negative`
- `CHECK (qty_reserved <= qty_on_hand)` named `ck_erp_stock_levels_reserved_leq_hand`

> This table is a **read optimization**. The source of truth is `erp_stock_movements`. Stock levels are recomputed after each movement (§4.1). No materialized view — decision recorded in ADR-000 (see §14.1).

### 3.4 `erp_stock_movements` — the ledger (the most important table)

| Column | Type / Constraint | Why it exists |
|---|---|---|
| `tenant_id` | UUID, NOT NULL, indexed | Ownership + RLS key |
| `product_id` | UUID, NOT NULL | FK → `erp_products.id` (composite with tenant) |
| `warehouse_id` | UUID, NOT NULL | FK → `erp_warehouses.id` (composite with tenant) |
| `type` | Enum, NOT NULL | `receive / adjust / transfer / sale / return` (native enum `erp_stock_movement_type`) |
| `qty` | Integer, NOT NULL | Signed delta (`+` in, `-` out). Must be `!= 0` |
| `ref_type` | String(32), nullable | What caused it, e.g. `sale_order`, `purchase_receipt` |
| `ref_id` | UUID, nullable | ID of the causing record |
| `reason` | String(255), nullable | **Required for `adjust`** (service-enforced) |
| `occurred_at` | timestamptz, NOT NULL default now() | When the movement happened |

**Rule: movements are immutable.** No UPDATE, no DELETE — enforced by service convention and never exposed via update/delete endpoints. The `qty != 0` guarantee is service-enforced (a `CHECK` is optional).

---

## 4. Business rules (the heart of the module)

All rules are implemented in the **service layer** (`features/inventory/service.py`). They execute inside a single DB transaction.

### 4.1 Rule 1 — Stock is a ledger
1. Every change to stock writes exactly one `erp_stock_movements` row.
2. After the movement row is written, `qty_on_hand` is **recomputed** on the affected `erp_stock_levels` row:
   `qty_on_hand = qty_on_hand + movement.qty` (signed).
3. If no stock level row exists for `(product, warehouse)`, create one in the same transaction (with `qty_on_hand` seeded from the movement).
4. Read endpoints always return the stored `qty_on_hand` (the recomputed value).

### 4.2 Rule 2 — No negative stock
1. **Service check:** before writing a movement with negative `qty`, verify `current_qty_on_hand + movement.qty >= 0`. If it would go negative → raise `InsufficientStockError` (409).
2. **DB backup:** the `CHECK (qty_on_hand >= 0)` constraint (§3.3) rejects any write that violates it.
3. Applies to `sale`, `transfer` (source side), and negative `adjust`.

### 4.3 Rule 3 — Transfers are atomic
1. `transfer_stock` writes **two** movements in one transaction:
   - Source warehouse: `type="transfer"`, `qty = -amount`
   - Destination warehouse: `type="transfer"`, `qty = +amount`
2. Both stock levels are recomputed in the same transaction.
3. If either write fails (e.g. source would go negative), the **entire transaction rolls back** — no partial movements.
4. Source must be != destination (else 422).

### 4.4 Rule 4 — Reorder alerts fire once per breach crossing
1. After recomputing `qty_on_hand`, compare against `product.reorder_point`.
2. A **breach crossing** = level transitions from `> reorder_point` to `<= reorder_point`. Track the previous level (from before this movement).
3. Fire **once** per crossing: emit `inventory.stock.level_changed` (§9) and write an audit row.
4. Repeated writes while already `<= reorder_point` do **not** re-fire.

---

## 5. Architecture

### 5.1 Service layout (`services/core`)

```
services/core/
├── src/core/
│   ├── api/
│   │   ├── deps.py                      # auth / tenant / permission deps (shared)
│   │   ├── lifespan.py
│   │   ├── middleware.py
│   │   ├── readiness.py
│   │   └── v1/
│   │       ├── router.py                # mounts feature routers at /api/v1
│   │       └── health.py
│   ├── core/                            # cross-cutting (mirrors identity's core/)
│   │   ├── config.py                    # env prefix CORE_
│   │   ├── permissions.py               # ERP permission catalog + require_permission
│   │   ├── exceptions.py                # RFC 7807 mapping
│   │   ├── constants.py
│   │   ├── tenant_context.py            # ContextVar pattern
│   │   ├── tenant_resolver.py
│   │   ├── audit_events.py              # canonical action constants
│   │   └── events/constants.py          # topic constants (inventory.stock.level_changed)
│   ├── db/
│   │   ├── base.py                      # Base, UUIDPrimaryKeyMixin, TimestampMixin
│   │   ├── session.py                   # engine + after_begin RLS set_config
│   │   └── repository.py                # SqlRepository base
│   ├── domain/
│   │   ├── entities.py                  # Product, Warehouse, StockLevel, StockMovement
│   │   └── value_objects.py             # Money
│   ├── events/
│   │   ├── consumers/                   # empty in Phase 1
│   │   ├── handlers/
│   │   └── producers/
│   │       └── stock_events.py          # emit inventory.stock.level_changed
│   ├── features/
│   │   └── inventory/                   # ★ THIS MODULE
│   │       ├── __init__.py
│   │       ├── router.py                # endpoints (thin)
│   │       ├── schemas.py               # Pydantic request/response
│   │       ├── service.py               # business rules (§4)
│   │       ├── ports.py                 # Protocol interfaces
│   │       └── repository.py            # SQLAlchemy access (tenant-scoped)
│   ├── models/
│   │   ├── base.py
│   │   ├── erp_product.py
│   │   ├── erp_warehouse.py
│   │   ├── erp_stock_level.py
│   │   └── erp_stock_movement.py
│   ├── main.py
│   └── seed.py                          # reference data only
├── alembic/
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│       └── 0001_initial.py              # all erp_* tables + RLS + enums
├── tests/
│   ├── unit/features/inventory/
│   ├── integration/api/inventory/
│   └── factories/
├── Dockerfile
└── pyproject.toml
```

### 5.2 Layering contract (must hold)

```
router → service → repository → models
```

| Layer | Responsibility | Must NOT do |
|---|---|---|
| `router.py` | HTTP marshalling, permission deps, call service | Business logic, DB access |
| `service.py` | Business rules (§4), orchestration, audit + events | Touch SQLAlchemy directly |
| `ports.py` | `Protocol` interfaces for repo + reservation consumers | Implementation |
| `repository.py` | All SQLAlchemy; **enforces `tenant_id` on every query** | Business rules |
| `models.py` | ORM mapping of §3 tables | Anything else |

No direct DB access from API or event handlers. Tenant scoping is enforced in the repository layer, never trusted to caller discipline.

### 5.3 Feature package files (copy identity's conventions)

- **`router.py`** — FastAPI `APIRouter`, module-level permission dependency singletons (e.g. `_require_inventory_read = require_permission(INVENTORY_READ)`), delegate to service, wrap responses in `ResponseEnvelope`.
- **`schemas.py`** — Pydantic request/response models (the API boundary).
- **`service.py`** — takes ports + sibling services in the constructor (wired only in `api/deps.py`).
- **`ports.py`** — `Protocol` classes; the service depends on these, not on the repository.
- **`repository.py`** — subclasses `SqlRepository`; maps entity ↔ ORM; every query filters `.where(Model.tenant_id == tenant_id)`.

### 5.4 Reservation port (called by CRM, built now)

Expose these service methods (CRM will call them via the same service object or an injected port):

| Method | Behavior |
|---|---|
| `reserve_stock(product_id, warehouse_id, qty)` | `qty_reserved += qty`; must satisfy `qty_reserved <= qty_on_hand` (else 409) |
| `release_reservation(product_id, warehouse_id, qty)` | `qty_reserved -= qty` (never below 0) |
| `fulfil_order(product_id, warehouse_id, qty)` | `qty_reserved -= qty`, write a `sale` movement, recompute level — one transaction |

Phase-1 semantics: **direct in-service call** (see §14.2 — confirm with team).

---

## 6. Multi-tenancy & RLS

Mirror the identity service exactly. RLS is the primary isolation; the repository `tenant_id` filter is defense-in-depth.

### 6.1 The SQL function (created once in migration `0001`)
```sql
CREATE FUNCTION public.current_tenant_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
$$;
```

### 6.2 Per-table policy (one per `erp_*` tenant-scoped table)
```sql
ALTER TABLE public.erp_stock_movements ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_erp_stock_movements ON public.erp_stock_movements
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());
```
Apply the same for `erp_products`, `erp_warehouses`, `erp_stock_levels`.

### 6.3 Setting the tenant per transaction (`db/session.py`)
```python
@event.listens_for(_sync_session_factory, "after_begin")
def _set_rls_tenant_context(_session, _transaction, connection) -> None:
    tenant_id = TenantContext.get_optional()
    if tenant_id is None:
        return
    connection.exec_driver_sql(
        "SELECT set_config('app.current_tenant_id', $1, true)", (tenant_id,)
    )
```
The third argument `true` makes the setting **transaction-local** (auto-reset at COMMIT/ROLLBACK).

### 6.4 Tenant resolution (once per request, in middleware)
1. Derive slug: production → Host subdomain; dev/test → `X-Tenant-Slug` header (never trust the header in prod).
2. Look up the tenant; unknown → 404, disabled → 403.
3. Verify JWT (if present) and cross-check its `tenant_id` against the routed tenant (mismatch → 401).
4. Store in `TenantContext` (ContextVar); reset in `finally`.

### 6.5 Composite foreign keys
Every FK from a tenant-scoped table to another tenant-scoped table **includes `tenant_id`** so RLS joins never leak:
```sql
CONSTRAINT fk_erp_stock_movements_product
  FOREIGN KEY (tenant_id, product_id) REFERENCES erp_products (tenant_id, id)
```
Apply to: `erp_stock_levels → erp_products`, `erp_stock_levels → erp_warehouses`, `erp_stock_movements → erp_products`, `erp_stock_movements → erp_warehouses`. Reference tables (`erp_currencies`, `erp_countries`) are global and read-only.

### 6.6 Tenant error mapping
| Condition | Status | Problem type |
|---|---|---|
| Tenant context missing | 400 | `tenant-context-missing` |
| JWT tenant ≠ routed tenant | 401 | `tenant-mismatch` |
| Tenant slug unknown | 404 | `tenant-not-found` |
| Tenant disabled | 403 | `tenant-disabled` |

---

## 7. Auth & permissions

### 7.1 How permissions work (important)
Permissions are **resolved from the database at request time** — they are **NOT** a JWT claim. `require_permission("erp.inventory.write")` resolves the user's roles → permissions on every request, fail-closed.

### 7.2 New permission keys (add to identity's catalog + seed)
| Key | Purpose |
|---|---|
| `erp.inventory.read` | View products, warehouses, stock, movements, alerts |
| `erp.inventory.write` | Create/update products, warehouses; adjustments, transfers |
| `erp.inventory.approve` | Approve large adjustments (delta above threshold, §14.3) |

Where to add (identity service):
- `services/identity/src/identity/core/permissions.py` — constants + `CATALOG` + `PERMISSION_MODULES`
- A new identity Alembic migration inserting the keys into `permissions` (`ON CONFLICT (key) DO NOTHING`)
- Identity `core/constants.py` `SYSTEM_ROLE_DEFINITIONS` — `tenant_owner`/`organization_admin` get all three; `department_manager` gets `erp.inventory.*`; `standard_user`/`auditor` get `erp.inventory.read`.

### 7.3 Endpoint permission usage
Module-level singleton dependencies in `router.py`:
```python
_require_inventory_read = require_permission(INVENTORY_READ)
_require_inventory_write = require_permission(INVENTORY_WRITE)
_require_inventory_approve = require_permission(INVENTORY_APPROVE)
```

---

## 8. API surface

All endpoints are under `/api/v1/inventory`, require a valid access JWT + tenant context, and check permissions server-side. Responses wrapped in `ResponseEnvelope`. List endpoints use offset/limit pagination (§10.4).

| # | Method & Path | Permission | Request → Response |
|---|---|---|---|
| 1 | `GET /api/v1/inventory/products` | `erp.inventory.read` | `?page=&page_size=&category=` → list of `ProductResponse` |
| 2 | `POST /api/v1/inventory/products` | `erp.inventory.write` | `ProductCreate` → `ProductResponse` |
| 3 | `GET /api/v1/inventory/warehouses` | `erp.inventory.read` | → list of `WarehouseResponse` |
| 4 | `POST /api/v1/inventory/warehouses` | `erp.inventory.write` | `WarehouseCreate` → `WarehouseResponse` |
| 5 | `GET /api/v1/inventory/stock` | `erp.inventory.read` | `?product_id=&warehouse_id=` → `StockLevelResponse` (list or single) |
| 6 | `POST /api/v1/inventory/stock/adjustments` | `erp.inventory.write`; delta > threshold → `erp.inventory.approve` | `StockAdjustmentCreate` (product, warehouse, qty, reason) → `StockMovementResponse` |
| 7 | `POST /api/v1/inventory/stock/transfers` | `erp.inventory.write` | `StockTransferCreate` (product, from_warehouse_id, to_warehouse_id, qty) → two `StockMovementResponse` |
| 8 | `GET /api/v1/inventory/stock/movements` | `erp.inventory.read` | `?product_id=&warehouse_id=&type=&page=&page_size=` → list |
| 9 | `GET /api/v1/inventory/alerts` | `erp.inventory.read` | → list of products currently `qty_on_hand <= reorder_point` |

### 8.1 Schema shapes (abridged)
```python
ProductCreate    { sku: str, name: str, category?: str, unit: str,
                   cost_price: Money, sell_price: Money, reorder_point: int }
StockAdjustmentCreate { product_id: UUID, warehouse_id: UUID, qty: int,
                        reason: str }  # reason required
StockTransferCreate    { product_id: UUID, from_warehouse_id: UUID,
                        to_warehouse_id: UUID, qty: int }
```

---

## 9. Events

### 9.1 Topic constant
Define once (new — no constants exist yet):
```python
# core/events/constants.py
INVENTORY_STOCK_LEVEL_CHANGED = "inventory.stock.level_changed"
```

### 9.2 Emit pattern (Phase 1)
Phase 1 has **no Kafka** — identity's producers are structlog-only stubs. Emit after commit:
1. Write the movement + audit row in the transaction.
2. Call `emit_stock_level_changed(product_id, warehouse_id, qty_on_hand, reorder_point, tenant_id)` in `events/producers/stock_events.py`.
3. That helper logs the event via structlog (keyed by tenant) using the `skyrict_events.BaseEvent` envelope shape (`event_id, event_type, timestamp, tenant_id, version, correlation_id, metadata`).
4. When Kafka wiring lands, this becomes a `BaseProducer.publish(...)` call — no call-site change.

### 9.3 Payload (event `details` / metadata)
```json
{ "product_id": "...", "warehouse_id": "...",
  "qty_on_hand": 12, "reorder_point": 10, "breach_crossed": true }
```

---

## 10. Cross-cutting

### 10.1 Money value object (new — create it)
```python
@dataclass(frozen=True)
class Money:
    amount: Decimal          # never float
    currency: str = "USD"    # validated against erp_currencies
```
- Arithmetic uses `Decimal`; currency validated in `__post_init__` against the seeded `erp_currencies` reference table.
- Model columns store `Numeric(18,4)`; schemas serialize as decimal strings.

### 10.2 Idempotency
No `Idempotency-Key` pattern exists in the codebase. Use **naturally idempotent** writes (probe before insert), matching identity:
- Adjustment: reject if a movement with the same `(ref_type, ref_id)` already exists (caller supplies a ref).
- Transfer: same probe.
- Reserve/fulfil: guarded increments.

### 10.3 Audit integration
Every mutation writes an audit row via the shared audit service:
```python
await self.audit_service.log(
    action=INVENTORY_STOCK_ADJUSTED,          # from core/audit_events.py
    target=f"stock_movement:{movement_id}",
    user_id=str(actor_user_id),
    tenant_id=str(tenant_id),
    ip_address=..., user_agent=...,
)
```
Canonical actions to add in `core/audit_events.py`: `inventory.product.created`, `inventory.product.updated`, `inventory.warehouse.created`, `inventory.stock.adjusted`, `inventory.stock.transferred`, `inventory.stock.reorder_alerted`.

### 10.4 Pagination
Use **offset/limit** (matches identity; no cursor pagination exists):
`PaginationParams(page=1, page_size=20)` from `skyrict-common`; responses wrapped in `ResponseEnvelope` / `ListResponse` with `PaginationMeta`.

### 10.5 Errors
Reuse `skyrict_common` exceptions → RFC 7807 `{type, status, title, detail, instance}` via `core/exceptions.py`. Add service exceptions: `InsufficientStockError` (409), `DuplicateSkuError` (409), `MovementImmutableError` (409), `TransferRequiresDistinctWarehousesError` (422).

### 10.6 Soft delete
Financial/order records are never hard-deleted: products/warehouses use `is_active = false`.

---

## 11. Build checklist (do in order)

| # | Task | Builds from | Verify with |
|---|---|---|---|
| 1 | Create `services/core` skeleton + config (`core/config.py`, env prefix `CORE_`; `CORE_DEFAULT_CURRENCY`, `CORE_INVENTORY_ADJUST_APPROVE_THRESHOLD`) | §5 | Unit test that `Settings()` loads |
| 2 | Add `Money` value object | §10.1 | `test_value_objects.py` |
| 3 | Add domain entities (`Product`, `Warehouse`, `StockLevel`, `StockMovement`) | §5.3 | dataclass invariant tests |
| 4 | Write Alembic `0001_initial` (4 tables, enums, constraints, composite FKs, RLS policies §6, seed `erp_currencies`) | §3, §6 | `alembic upgrade head` against Postgres |
| 5 | Build `repository.py` (tenant-scoped queries, `add_movement`, `recompute_stock_level`, `get_stock_level`, probes) | §5.2, §6.4 | repository integration tests |
| 6 | Define `ports.py` Protocols | §5.3 | — |
| 7 | Implement `service.py` business rules (§4) + reservation methods (§5.4) | §4, §5.4 | `test_service.py` (unit) |
| 8 | Write `schemas.py` + `router.py` endpoints (§8) with permission deps (§7) | §7, §8 | contract tests via ASGI client |
| 9 | Add `stock_events.py` emitter + topic constant + audit actions | §9, §10.3 | unit test assert event logged |
| 10 | Add `erp.inventory.*` keys to identity catalog + migration + role seed | §7.2 | identity unit/integration tests |
| 11 | Write integration tests: two-tenant isolation + per-warehouse isolation + acceptance criteria (§12) | §12 | `pytest tests/integration` |

---

## 12. Testing & acceptance criteria

### 12.1 Unit tests (`tests/unit/features/inventory/`)
- Money: Decimal arithmetic, currency validation, no float
- Rule 1: movement row written + stock level recomputed
- Rule 2: negative stock rejected in service; `CHECK` rejects at DB
- Rule 3: transfer writes 2 movements; failure rolls back both
- Rule 4: alert fires once per breach crossing, not repeatedly
- Reservation: `qty_reserved` never exceeds `qty_on_hand`

### 12.2 Integration tests (`tests/integration/api/inventory/`)
Mirror `test_tenant_isolation.py`: real Postgres + `alembic upgrade head`, provision two tenants via `X-Tenant-Slug`.
- Tenant A's products/stock/movements are invisible to tenant B (all read/write endpoints → 404/empty, never data)
- Per-warehouse isolation within one tenant
- Cross-tenant token + slug → 401 `tenant-mismatch`

### 12.3 Acceptance criteria (Definition of Done)
- [ ] No negative stock — enforced in service **and** DB
- [ ] Movements immutable — no update/delete endpoints or repo methods
- [ ] Transfer is one atomic transaction (2 movements or none)
- [ ] Reorder alert fires once per breach crossing
- [ ] Tenant isolation + per-warehouse isolation verified with two tenants
- [ ] Every adjustment/transfer audited
- [ ] Reservation flow satisfies `qty_reserved <= qty_on_hand`

---

## 13. Frontend / BFF (not your build, but be aware)

- BFF route handlers proxy `/api/erp/inventory/*` same-origin (mirroring the auth BFF discipline)
- Sidebar filter key: `erp.inventory.read` (UI only — enforcement is server-side)
- Plan gating (billing) decides module visibility; enforced externally (SKY-32..36)

---

## 14. Open decisions (confirm with the team before/at build time)

| # | Decision | Recommended default (per ERP plan) |
|---|---|---|
| 1 | Stock-level storage: recompute-on-write vs materialized view | **Recompute-on-write** (record in ADR-000) |
| 2 | Reservation semantics in Phase 1 | **Direct in-service call** (not outbox) |
| 3 | Adjustment-approve threshold value | Configurable (`CORE_INVENTORY_ADJUST_APPROVE_THRESHOLD`), default e.g. 100 |
| 4 | Idempotency: probe-based vs `Idempotency-Key` header | **Probe-based** (matches identity; header = new pattern) |

---

## 15. Corrections to the ERP plan (research findings)

These differ from the Phase-1 plan document — follow this doc:
1. **Permissions are NOT a JWT claim** — resolved from the DB at request time via `require_permission`.
2. **No cursor pagination exists** — use offset/limit + `PaginationMeta`.
3. **No `Idempotency-Key` pattern exists** — use naturally idempotent probe-based writes.
4. **`libs/skyrict-logging` does not exist** — logging lives in `skyrict-common/logging.py`.
5. **Kafka is stub/logging-only today** — emit events as structlog + audit rows; no hard Kafka dependency in Phase 1.
6. **Tenant error codes are not all 403** — missing=400, mismatch=401, unknown=404, disabled=403.

---

## 16. Related documents
- ERP Phase 1 plan (source of this spec)
- `services/identity` — feature-package structure, RLS mechanics, permission/tenant source of truth
- `docs/architecture/adr/*` — ADR-001 (uv workspaces), ADR-002 (single identity service), ADR-003 (staging DNS/TLS), ADR-004 (login security posture)
- `libs/skyrict-common`, `libs/skyrict-events` (`src/skyrict_events/base.py`)
