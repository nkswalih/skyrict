"""Revenue-forecast persistence (SKY-82 A4).

Reads the recognized-revenue series from approved invoices (the same source
boundary as finance: revenue is only recognized at ``approved``), and upserts
forecast rows keyed on ``UNIQUE (tenant_id, month)`` - the recompute guard.

Pipeline weighting reads the tenant's open CRM opportunities (same shared
database, tenant-scoped) - weighted conversion value per closing month is
``probability/100 x amount`` of every non-terminal deal whose
``expected_close_date`` lands in the forecast horizon, modulated by the deal's
latest health assessment. ``ai_deal_health`` is owned by the ai-agent service
but lives in the same shared database, so core reads it read-only (tenant-
scoped by the same RLS GUC) and blends its green/yellow/red band with the
assessment's confidence into the per-deal conversion weight. Deals the health
engine has never assessed keep their full weight. If the table is absent (e.g.
an environment where the ai-agent chain has not migrated yet), weighting
degrades to the unmodulated ``probability/100 x amount`` baseline.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Column, DateTime, Float, MetaData, String, Table, func, select
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.value_objects import InvoiceStatus, OpportunityStage
from core.features.crm.models.opportunity import ErpCrmOpportunityModel
from core.features.finance.models.invoice import ErpInvoiceModel
from core.features.revenue_forecast.calculator import (
    MonthlyRevenue,
    deal_health_factor,
)
from core.features.revenue_forecast.models.forecast import ErpRevenueForecastModel

logger = logging.getLogger(__name__)

# ai-agent-owned deal-health feed (same shared DB, read-only in core). Read via
# a local table definition so core never owns or migrates the table.
_ai_deal_health = Table(
    "ai_deal_health",
    MetaData(),
    Column("tenant_id", UUID(as_uuid=True)),
    Column("opportunity_id", UUID(as_uuid=True)),
    Column("health", String(16)),
    Column("confidence", Float),
    Column("computed_at", DateTime(timezone=True)),
)


@dataclass(frozen=True)
class PipelineDeal:
    """One open CRM deal weighted into a forecast month.

    ``weighted`` is the raw conversion value (``probability/100 x amount``);
    ``adjusted`` applies the latest deal-health factor (green keeps the full
    weight, yellow/red discount it, blended toward neutral by confidence)
    and is what month totals are built from - so per-deal detail always sums
    to the month's pipeline.
    """

    id: uuid.UUID
    name: str
    amount: Decimal | None
    probability: int
    expected_close_date: date
    month: date
    weighted: Decimal
    health: str | None
    confidence: float | None
    factor: Decimal
    adjusted: Decimal


class RevenueForecastRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def monthly_revenue(self, tenant_id: uuid.UUID, from_month: date) -> list[MonthlyRevenue]:
        """Recognized revenue per calendar month from approved invoices."""
        result = await self._db.execute(
            select(
                func.date_trunc("month", ErpInvoiceModel.invoice_date).label("month"),
                func.sum(ErpInvoiceModel.total).label("revenue"),
            )
            .where(
                ErpInvoiceModel.tenant_id == tenant_id,
                ErpInvoiceModel.status == InvoiceStatus.APPROVED,
                ErpInvoiceModel.invoice_date >= from_month,
            )
            .group_by("month")
            .order_by("month")
        )
        return [
            MonthlyRevenue(month=row.month.date(), revenue=Decimal(row.revenue))
            for row in result.all()
        ]

    async def pipeline_deals(
        self, tenant_id: uuid.UUID, from_month: date, to_month: date
    ) -> list[PipelineDeal]:
        """Weighted expected pipeline deals per closing month in the horizon.

        Every open (non-terminal) opportunity with an amount and an
        ``expected_close_date`` inside ``[from_month, to_month]`` contributes
        ``probability/100 x amount`` to its closing month, scaled by the deal's
        latest health rating (:func:`deal_health_factor`): green keeps the full
        weight, yellow/red discounts it, and the discount is blended toward
        neutral by low assessment confidence. Deals without an amount or
        without an expected close date are ignored (they cannot be
        value-weighted or bucketed honestly). If the ai-agent's ``ai_deal_health``
        table is unavailable, deals keep their unmodulated weight.
        """
        result = await self._db.execute(
            select(
                ErpCrmOpportunityModel.id,
                ErpCrmOpportunityModel.name,
                ErpCrmOpportunityModel.amount,
                ErpCrmOpportunityModel.probability,
                ErpCrmOpportunityModel.expected_close_date,
                func.date_trunc("month", ErpCrmOpportunityModel.expected_close_date).label("month"),
                (ErpCrmOpportunityModel.amount * ErpCrmOpportunityModel.probability / 100).label(
                    "weighted"
                ),
            ).where(
                ErpCrmOpportunityModel.tenant_id == tenant_id,
                ErpCrmOpportunityModel.stage.not_in((OpportunityStage.WON, OpportunityStage.LOST)),
                ErpCrmOpportunityModel.amount.is_not(None),
                ErpCrmOpportunityModel.expected_close_date.is_not(None),
                ErpCrmOpportunityModel.expected_close_date >= from_month,
                ErpCrmOpportunityModel.expected_close_date <= to_month,
            )
        )
        rows = result.all()
        if not rows:
            return []
        assessments = await self._deal_health_assessments(tenant_id, [row.id for row in rows])
        deals: list[PipelineDeal] = []
        for row in rows:
            health, confidence = assessments.get(row.id, (None, None))
            factor = deal_health_factor(health, confidence)
            weighted = Decimal(row.weighted)
            deals.append(
                PipelineDeal(
                    id=row.id,
                    name=row.name,
                    amount=row.amount,
                    probability=row.probability,
                    expected_close_date=row.expected_close_date,
                    month=row.month.date(),
                    weighted=weighted,
                    health=health,
                    confidence=confidence,
                    factor=factor,
                    adjusted=(weighted * factor).quantize(
                        Decimal("0.0001"), rounding=ROUND_HALF_UP
                    ),
                )
            )
        return deals

    async def pipeline_by_month(
        self, tenant_id: uuid.UUID, from_month: date, to_month: date
    ) -> dict[date, Decimal]:
        """Weighted expected pipeline value per closing month in the horizon."""
        pipeline: dict[date, Decimal] = {}
        for deal in await self.pipeline_deals(tenant_id, from_month, to_month):
            pipeline[deal.month] = pipeline.get(deal.month, Decimal("0")) + deal.adjusted
        return pipeline

    async def _deal_health_assessments(
        self, tenant_id: uuid.UUID, opportunity_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str | None, float | None]]:
        """Latest health band + confidence per opportunity (missing -> unassessed).

        Reads the ai-agent-owned ``ai_deal_health`` table read-only, tenant-
        scoped (explicit filter + the same RLS GUC core's session sets). For
        each opportunity the most recently computed assessment wins. When the
        table is absent (ai-agent chain not yet migrated in this environment),
        every deal keeps its full weight and the forecast still computes.
        """
        if not opportunity_ids:
            return {}
        try:
            result = await self._db.execute(
                select(
                    _ai_deal_health.c.opportunity_id,
                    _ai_deal_health.c.health,
                    _ai_deal_health.c.confidence,
                )
                .where(
                    _ai_deal_health.c.tenant_id == tenant_id,
                    _ai_deal_health.c.opportunity_id.in_(opportunity_ids),
                )
                .order_by(_ai_deal_health.c.computed_at.desc())
            )
        except ProgrammingError as exc:
            logger.warning(
                "revenue_forecast.pipeline.deal_health_unavailable: %s",
                exc,
            )
            return {}
        latest: dict[uuid.UUID, tuple[str | None, float | None]] = {}
        for row in result.all():
            if row.opportunity_id not in latest:
                latest[row.opportunity_id] = (row.health, row.confidence)
        return latest

    async def replace_forecast(
        self,
        tenant_id: uuid.UUID,
        model_version: str,
        *,
        months: list[date],
        predicted: list[Decimal],
        lower_bounds: list[Decimal | None],
        upper_bounds: list[Decimal | None],
        sigma: Decimal | None,
        backtest_mape: Decimal | None,
        pipeline_value: Decimal | None = None,
        baselines: list[Decimal | None] | None = None,
        pipeline_uplifts: list[Decimal | None] | None = None,
    ) -> None:
        """Upsert the full forecast horizon for a tenant (recompute guard).

        ``pipeline_value`` is the run-level total of weighted expected pipeline
        added to the horizon (``None`` when the forecast abstained); it applies
        to every row written by this recompute. ``baselines`` / ``pipeline_uplifts``
        are the per-month decomposition (``predicted == baseline + pipeline_uplift``)
        aligned with ``months``; ``None`` means decomposition is not stored.
        """
        if months:
            baselines = baselines or [None] * len(months)
            pipeline_uplifts = pipeline_uplifts or [None] * len(months)
            stmt = insert(ErpRevenueForecastModel).values(
                [
                    {
                        "tenant_id": tenant_id,
                        "month": m,
                        "predicted": p,
                        "lower_bound": lo,
                        "upper_bound": hi,
                        "sigma": sigma,
                        "backtest_mape": backtest_mape,
                        "model_version": model_version,
                        "pipeline_value": pipeline_value,
                        "baseline": b,
                        "pipeline_uplift": pu,
                    }
                    for m, p, lo, hi, b, pu in zip(
                        months,
                        predicted,
                        lower_bounds,
                        upper_bounds,
                        baselines,
                        pipeline_uplifts,
                        strict=True,
                    )
                ]
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_erp_revenue_forecast_tenant_month",
                set_={
                    "predicted": stmt.excluded.predicted,
                    "lower_bound": stmt.excluded.lower_bound,
                    "upper_bound": stmt.excluded.upper_bound,
                    "sigma": stmt.excluded.sigma,
                    "backtest_mape": stmt.excluded.backtest_mape,
                    "model_version": stmt.excluded.model_version,
                    "pipeline_value": stmt.excluded.pipeline_value,
                    "baseline": stmt.excluded.baseline,
                    "pipeline_uplift": stmt.excluded.pipeline_uplift,
                    "updated_at": func.now(),
                },
            )
            await self._db.execute(stmt)

    async def get_forecast(self, tenant_id: uuid.UUID) -> list[ErpRevenueForecastModel]:
        result = await self._db.execute(
            select(ErpRevenueForecastModel)
            .where(ErpRevenueForecastModel.tenant_id == tenant_id)
            .order_by(ErpRevenueForecastModel.month)
        )
        return list(result.scalars().all())
