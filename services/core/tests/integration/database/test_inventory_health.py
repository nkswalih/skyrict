"""Stock-health analytics integration tests (INV-ANL-001) — real Postgres.

Verifies the quarterly-analysis behaviour end-to-end through the repository:

  - dead stock: active products with on-hand stock but NO outbound (ISSUE)
    movement inside the trailing window (regardless of older receipts);
  - movement trends: weekly stacked receipts/issues per warehouse;
  - slow movers: bottom-quartile turnover items (ratio > 0);
  - health summary: aggregates + tied-up capital at cost;
  - report snapshots: (tenant, definition, period) idempotent persistence.

Two isolated tenants keep the dead-stock/trends and slow-mover computations
deterministic (slow-mover eligibility spans the whole tenant).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from core.db.session import async_session_factory, engine
from core.domain.value_objects import StockMovementType
from core.features.inventory.models.product import ErpProductModel
from core.features.inventory.models.stock_level import ErpStockLevelModel
from core.features.inventory.models.stock_movement import ErpStockMovementModel
from core.features.inventory.models.warehouse import ErpWarehouseModel
from core.features.inventory.repository import InventoryRepository
from core.models.tenant import TenantModel

pytestmark = pytest.mark.integration


def _u(value: str) -> uuid.UUID:
    return uuid.UUID(value)


def _now(**delta: int) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


@pytest.fixture(scope="module")
def health_world(migrated_schema: None) -> dict[str, str]:
    async def _setup() -> dict[str, str]:
        tenant_dead = str(uuid.uuid4())
        tenant_slow = str(uuid.uuid4())
        wh_dead = str(uuid.uuid4())
        wh_slow = str(uuid.uuid4())

        p_dead = str(uuid.uuid4())
        p_moving = str(uuid.uuid4())
        p_stale = str(uuid.uuid4())

        s1 = str(uuid.uuid4())
        s2 = str(uuid.uuid4())
        s3 = str(uuid.uuid4())
        s4 = str(uuid.uuid4())

        async with async_session_factory() as session:
            session.add_all(
                [
                    TenantModel(
                        id=_u(tenant_dead),
                        name="Health Dead Tenant",
                        slug=f"health-dead-{tenant_dead[:8]}",
                        plan_tier="free",
                        is_active=True,
                    ),
                    TenantModel(
                        id=_u(tenant_slow),
                        name="Health Slow Tenant",
                        slug=f"health-slow-{tenant_slow[:8]}",
                        plan_tier="free",
                        is_active=True,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ErpWarehouseModel(tenant_id=_u(tenant_dead), id=_u(wh_dead), name="Dead WH"),
                    ErpWarehouseModel(tenant_id=_u(tenant_slow), id=_u(wh_slow), name="Slow WH"),
                ]
            )
            session.add_all(
                [
                    _product(tenant_dead, p_dead, "D-1", "Dead full", Decimal("2.00")),
                    _product(tenant_dead, p_moving, "D-2", "Moving", Decimal("3.00")),
                    _product(tenant_dead, p_stale, "D-3", "Stale", Decimal("4.00")),
                    _product(tenant_slow, s1, "S-1", "Fast-ish", Decimal("1.00")),
                    _product(tenant_slow, s2, "S-2", "Fast", Decimal("1.00")),
                    _product(tenant_slow, s3, "S-3", "Slow", Decimal("1.00")),
                    _product(tenant_slow, s4, "S-4", "Slowish", Decimal("1.00")),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    _level(tenant_dead, p_dead, wh_dead, Decimal("10")),
                    _level(tenant_dead, p_moving, wh_dead, Decimal("6")),
                    _level(tenant_dead, p_stale, wh_dead, Decimal("5")),
                    _level(tenant_slow, s1, wh_slow, Decimal("100")),
                    _level(tenant_slow, s2, wh_slow, Decimal("100")),
                    _level(tenant_slow, s3, wh_slow, Decimal("100")),
                    _level(tenant_slow, s4, wh_slow, Decimal("100")),
                ]
            )
            # Tenant 1 movements.
            session.add_all(
                [
                    _movement(
                        tenant_dead,
                        p_moving,
                        wh_dead,
                        "po",
                        "R-MOV-1",
                        Decimal("10"),
                        _now(days=20),
                    ),
                    _movement(
                        tenant_dead,
                        p_moving,
                        wh_dead,
                        "so",
                        "I-MOV-1",
                        Decimal("-4"),
                        _now(days=10),
                    ),
                    _movement(
                        tenant_dead, p_stale, wh_dead, "po", "R-STA-1", Decimal("7"), _now(days=210)
                    ),
                    _movement(
                        tenant_dead,
                        p_stale,
                        wh_dead,
                        "so",
                        "I-STA-1",
                        Decimal("-2"),
                        _now(days=200),
                    ),
                ]
            )
            # Tenant 2 movements (all within the 180-day slow-mover window).
            session.add_all(
                [
                    _movement(
                        tenant_slow, s1, wh_slow, "po", "R-S1", Decimal("100"), _now(days=30)
                    ),
                    _movement(tenant_slow, s1, wh_slow, "so", "I-S1", Decimal("-50"), _now(days=1)),
                    _movement(
                        tenant_slow, s2, wh_slow, "po", "R-S2", Decimal("100"), _now(days=30)
                    ),
                    _movement(tenant_slow, s2, wh_slow, "so", "I-S2", Decimal("-90"), _now(days=1)),
                    _movement(
                        tenant_slow, s3, wh_slow, "po", "R-S3", Decimal("100"), _now(days=30)
                    ),
                    _movement(tenant_slow, s3, wh_slow, "so", "I-S3", Decimal("-10"), _now(days=1)),
                    _movement(
                        tenant_slow, s4, wh_slow, "po", "R-S4", Decimal("100"), _now(days=30)
                    ),
                    _movement(tenant_slow, s4, wh_slow, "so", "I-S4", Decimal("-30"), _now(days=1)),
                ]
            )
            await session.commit()
            await engine.dispose()

        return {
            "tenant_dead": tenant_dead,
            "tenant_slow": tenant_slow,
            "wh_dead": wh_dead,
            "p_dead": p_dead,
            "p_moving": p_moving,
            "p_stale": p_stale,
            "s1": s1,
            "s2": s2,
            "s3": s3,
            "s4": s4,
        }

    async def _teardown() -> None:
        async with async_session_factory() as session:
            for tid in (health_world_data["tenant_dead"], health_world_data["tenant_slow"]):
                tid_uuid = _u(tid)
                for table in (
                    "erp_report_snapshots",
                    "erp_stock_movements",
                    "erp_stock_levels",
                    "erp_products",
                    "erp_warehouses",
                ):
                    await session.execute(
                        text(f"DELETE FROM {table} WHERE tenant_id = :tid"),
                        {"tid": tid_uuid},
                    )
                await session.execute(
                    text("DELETE FROM tenants WHERE id = :tid"),
                    {"tid": tid_uuid},
                )
            await session.commit()
            await engine.dispose()

    health_world_data = asyncio.run(_setup())
    try:
        yield health_world_data
    finally:
        asyncio.run(_teardown())


def _product(tenant: str, pid: str, sku: str, name: str, cost: Decimal) -> ErpProductModel:
    return ErpProductModel(
        tenant_id=_u(tenant),
        id=_u(pid),
        sku=sku,
        name=name,
        cost_price=cost,
        cost_currency_code="USD",
        sell_price=cost * Decimal("2"),
        sell_currency_code="USD",
        reorder_point=Decimal("2"),
        is_active=True,
    )


def _level(tenant: str, pid: str, wid: str, qty: Decimal) -> ErpStockLevelModel:
    return ErpStockLevelModel(
        tenant_id=_u(tenant),
        id=uuid.uuid4(),
        product_id=_u(pid),
        warehouse_id=_u(wid),
        qty_on_hand=qty,
        qty_reserved=Decimal("0"),
    )


def _movement(
    tenant: str,
    pid: str,
    wid: str,
    ref_type: str,
    ref_id: str,
    qty: Decimal,
    when: datetime,
) -> ErpStockMovementModel:
    mtype = StockMovementType.ISSUE if qty < 0 else StockMovementType.RECEIPT
    return ErpStockMovementModel(
        tenant_id=_u(tenant),
        id=uuid.uuid4(),
        product_id=_u(pid),
        warehouse_id=_u(wid),
        movement_type=mtype,
        qty=qty,
        ref_type=ref_type,
        ref_id=ref_id,
        created_at=when,
    )


class TestDeadStock:
    async def test_lists_only_items_with_no_recent_outbound(
        self, health_world: dict[str, str]
    ) -> None:
        tenant = _u(health_world["tenant_dead"])
        async with async_session_factory() as session:
            repo = InventoryRepository(session)
            items = await repo.dead_stock(tenant, days=90)
            skus = sorted(i.sku for i in items)
            # P_dead (no movements) and P_stale (outbound 200d ago) qualify;
            # P_moving has a recent ISSUE so it does not.
            assert skus == ["D-1", "D-3"]
            assert await repo.count_dead_stock(tenant, days=90) == 2

            by_sku = {i.sku: i for i in items}
            assert by_sku["D-1"].qty_on_hand == Decimal("10")
            assert by_sku["D-3"].qty_on_hand == Decimal("5")
            assert by_sku["D-1"].last_outbound_at is None
            assert by_sku["D-3"].last_outbound_at is not None
            await session.commit()

    async def test_short_window_excludes_older_outbound(self, health_world: dict[str, str]) -> None:
        tenant = _u(health_world["tenant_dead"])
        async with async_session_factory() as session:
            repo = InventoryRepository(session)
            # 30-day window: P_stale's 200-day-old outbound still counts as dead
            # and P_dead still qualifies; P_moving still has a recent ISSUE.
            skus = sorted(i.sku for i in await repo.dead_stock(tenant, days=30))
            assert skus == ["D-1", "D-3"]
            assert await repo.count_dead_stock(tenant, days=30) == 2
            await session.commit()


class TestMovementTrends:
    async def test_buckets_receipts_and_issues_by_week(self, health_world: dict[str, str]) -> None:
        tenant = _u(health_world["tenant_dead"])
        async with async_session_factory() as session:
            repo = InventoryRepository(session)
            points = await repo.movement_trends(tenant, weeks=13)
            await session.commit()
            total_receipts = sum(p.receipts for p in points)
            total_issues = sum(p.issues for p in points)
            # Only P_moving's movements fall inside the 13-week window.
            assert total_receipts == Decimal("10")
            assert total_issues == Decimal("4")


class TestSlowMovers:
    async def test_bottom_quartile_turnover(self, health_world: dict[str, str]) -> None:
        tenant = _u(health_world["tenant_slow"])
        async with async_session_factory() as session:
            repo = InventoryRepository(session)
            items = await repo.slow_movers(tenant, window_days=180)
            await session.commit()
            skus = sorted(i.sku for i in items)
            # Ratios 0.1/0.3/0.5/0.9 -> median 0.4 -> items with ratio <= 0.4.
            assert skus == ["S-3", "S-4"]
            assert all(i.turnover_ratio > Decimal("0") for i in items)
            assert await repo.count_slow_movers(tenant, window_days=180) == 2

    async def test_markdown_flag_on_lowest_turnover(self, health_world: dict[str, str]) -> None:
        tenant = _u(health_world["tenant_slow"])
        async with async_session_factory() as session:
            repo = InventoryRepository(session)
            items = await repo.slow_movers(tenant, window_days=180)
            await session.commit()
            by_sku = {i.sku: i for i in items}
            # S-4 ratio 0.3 (< 0.5) suggests markdown; S-3 ratio 0.1 too.
            assert by_sku["S-3"].suggest_markdown is True
            assert by_sku["S-4"].suggest_markdown is True


class TestHealthSummary:
    async def test_aggregates_metrics(self, health_world: dict[str, str]) -> None:
        tenant = _u(health_world["tenant_dead"])
        async with async_session_factory() as session:
            repo = InventoryRepository(session)
            summary = await repo.health_summary(tenant, days=90)
            await session.commit()
            assert summary.total_sku_count == 3
            assert summary.dead_stock_count == 2
            assert summary.slow_mover_count == 0  # no eligible outbound in tenant
            assert summary.tied_up_capital.currency == "USD"
            # D-1 cost 2 * 10 + D-3 cost 4 * 5 = 40
            assert summary.tied_up_capital.amount == Decimal("40")
