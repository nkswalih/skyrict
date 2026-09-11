"""Revenue-forecast pipeline weighting integration tests (SKY-82 A4).

``RevenueForecastRepository.pipeline_by_month`` against REAL Postgres. It must
hold in both environments it runs in: a core-only database where the ai-agent
chain has not migrated (``ai_deal_health`` is absent, so the reader must
degrade to unmodulated conversion-probability weights) and a shared database
where the table exists and a live assessment feed is present. Both converge to
the same behavior here, because no ``ai_deal_health`` rows exist for this
tenant: the expected outcome is full ``probability/100 x amount`` weighting.

Terminal (``won``/``lost``) and null-amount / null-close-opportunities, and
deals closing outside the horizon window, must be excluded from the bucketed
weighted pipeline.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from core.db.session import async_session_factory, engine
from core.domain.value_objects import OpportunityStage
from core.features.crm.models.opportunity import ErpCrmOpportunityModel
from core.features.revenue_forecast.repository import RevenueForecastRepository
from core.models.tenant import TenantModel

pytestmark = pytest.mark.integration

FROM_MONTH = date(2026, 7, 1)
TO_MONTH = date(2026, 9, 30)


@pytest.fixture(scope="module")
def pipeline_world(migrated_schema: None) -> dict[str, str]:
    """Seed one tenant plus a spread of CRM opportunities.

    Plain (sync) fixture: all DB work runs inside one ``asyncio.run()`` and the
    engine pool is disposed before that run's loop closes, so the function-
    scoped async tests that follow get a clean pool bound to their own loops.
    """

    async def _setup() -> dict[str, str]:
        tenant_id = uuid.uuid4()
        async with async_session_factory() as session:
            session.add(
                TenantModel(
                    id=tenant_id,
                    name="Forecast Pipeline Tenant",
                    slug=f"pl-{tenant_id.hex[:8]}",
                    plan_tier="free",
                    is_active=True,
                )
            )
            await session.flush()
            session.add_all(
                [
                    ErpCrmOpportunityModel(
                        tenant_id=tenant_id,
                        name="Qualified A",
                        stage=OpportunityStage.QUALIFIED,
                        amount=Decimal("10000.0000"),
                        currency_code="USD",
                        probability=50,
                        expected_close_date=date(2026, 7, 15),
                    ),
                    ErpCrmOpportunityModel(
                        tenant_id=tenant_id,
                        name="Proposal B",
                        stage=OpportunityStage.PROPOSAL,
                        amount=Decimal("20000.0000"),
                        currency_code="USD",
                        probability=80,
                        expected_close_date=date(2026, 8, 20),
                    ),
                    ErpCrmOpportunityModel(
                        tenant_id=tenant_id,
                        name="Negotiation C",
                        stage=OpportunityStage.NEGOTIATION,
                        amount=Decimal("30000.0000"),
                        currency_code="USD",
                        probability=100,
                        expected_close_date=date(2026, 8, 28),
                    ),
                    # Excluded: terminal stages.
                    ErpCrmOpportunityModel(
                        tenant_id=tenant_id,
                        name="Lost D",
                        stage=OpportunityStage.LOST,
                        amount=Decimal("50000.0000"),
                        currency_code="USD",
                        probability=90,
                        expected_close_date=date(2026, 8, 1),
                        lost_at=datetime(2026, 8, 2),
                    ),
                    ErpCrmOpportunityModel(
                        tenant_id=tenant_id,
                        name="Won E",
                        stage=OpportunityStage.WON,
                        amount=Decimal("40000.0000"),
                        currency_code="USD",
                        probability=100,
                        expected_close_date=date(2026, 7, 10),
                        won_at=datetime(2026, 7, 10),
                    ),
                    # Excluded: no amount, no close date, outside the window.
                    ErpCrmOpportunityModel(
                        tenant_id=tenant_id,
                        name="No Amount F",
                        stage=OpportunityStage.PROSPECTING,
                        amount=None,
                        currency_code=None,
                        probability=20,
                        expected_close_date=date(2026, 7, 1),
                    ),
                    ErpCrmOpportunityModel(
                        tenant_id=tenant_id,
                        name="No Close Date G",
                        stage=OpportunityStage.PROSPECTING,
                        amount=Decimal("90000.0000"),
                        currency_code="USD",
                        probability=25,
                        expected_close_date=None,
                    ),
                    ErpCrmOpportunityModel(
                        tenant_id=tenant_id,
                        name="Outside Horizon H",
                        stage=OpportunityStage.QUALIFIED,
                        amount=Decimal("70000.0000"),
                        currency_code="USD",
                        probability=40,
                        expected_close_date=date(2026, 10, 15),
                    ),
                ]
            )
            await session.commit()
            await engine.dispose()
        return {"tenant_id": str(tenant_id)}

    async def _teardown(created: str) -> None:
        async with async_session_factory() as session:
            await session.execute(
                text("DELETE FROM tenants WHERE id = :tid"), {"tid": uuid.UUID(created)}
            )
            await session.commit()
            await engine.dispose()

    created = asyncio.run(_setup())
    try:
        yield created
    finally:
        asyncio.run(_teardown(created["tenant_id"]))


async def test_pipeline_by_month_buckets_only_open_winning_window_deals(
    pipeline_world: dict[str, str],
) -> None:
    tenant_id = uuid.UUID(pipeline_world["tenant_id"])
    async with async_session_factory() as session:
        repo = RevenueForecastRepository(session)
        pipeline = await repo.pipeline_by_month(tenant_id, FROM_MONTH, TO_MONTH)
        await session.rollback()

    # A = 10000 x 50% = 5000 (Jul); B + C = 20000x80% + 30000x100% = 46000 (Aug).
    assert pipeline == {
        date(2026, 7, 1): Decimal("5000"),
        date(2026, 8, 1): Decimal("46000"),
    }
