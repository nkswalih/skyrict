"""Revenue-forecast service (SKY-82 A4).

``refresh`` computes and persists a 12-month forecast (damped trend +
seasonal echo, plus an additive CRM pipeline uplift) from the last 24 months
of recognized revenue (abstaining - persisting nothing - when there is under
3 months of history); ``read`` returns whatever is currently stored (weekly
recompute and manual refresh keep it fresh). The pipeline uplift weights the
tenant's open CRM opportunities at their conversion probability
(``probability/100 x amount`` per closing month, modulated by each deal's
latest ai-agent deal-health rating) and only shifts projected months - the
backtest/MAPE/band stay invoice-based.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from core.features.revenue_forecast.calculator import (
    HORIZON_MONTHS,
    MIN_HISTORY_MONTHS,
    MonthlyRevenue,
    compute_forecast,
    month_step,
)
from core.features.revenue_forecast.repository import PipelineDeal, RevenueForecastRepository
from core.features.revenue_forecast.schemas import (
    ActualPointResponse,
    ForecastDealResponse,
    ForecastPointResponse,
    RevenueForecastResponse,
)

_HISTORY_MONTHS = 24


def _deal_list_by_month(deals: list[PipelineDeal]) -> dict[date, list[PipelineDeal]]:
    by_month: dict[date, list[PipelineDeal]] = {}
    for deal in deals:
        by_month.setdefault(deal.month, []).append(deal)
    return by_month


class RevenueForecastService:
    def __init__(self, repo: RevenueForecastRepository) -> None:
        self._repo = repo

    @staticmethod
    def _history_from_month(as_of: date) -> date:
        year = as_of.year + (as_of.month - 1 - (_HISTORY_MONTHS - 1)) // 12
        month = (as_of.month - 1 - (_HISTORY_MONTHS - 1)) % 12 + 1
        return date(year, month, 1)

    @staticmethod
    def _history_response(monthly: list[MonthlyRevenue]) -> list[ActualPointResponse]:
        return [ActualPointResponse(month=row.month, actual=row.revenue) for row in monthly]

    @staticmethod
    def _deal_response(deal: PipelineDeal) -> ForecastDealResponse:
        return ForecastDealResponse(
            id=deal.id,
            name=deal.name,
            amount=deal.amount,
            probability=deal.probability,
            expected_close_date=deal.expected_close_date,
            weighted=deal.weighted,
            health=deal.health,
            confidence=deal.confidence,
            factor=deal.factor,
            adjusted=deal.adjusted,
        )

    async def refresh(
        self, tenant_id: uuid.UUID, as_of: date | None = None
    ) -> RevenueForecastResponse:
        as_of = as_of or date.today()
        monthly = await self._repo.monthly_revenue(tenant_id, self._history_from_month(as_of))

        pipeline_value: Decimal | None = None
        deals: list[PipelineDeal] = []
        if len(monthly) >= MIN_HISTORY_MONTHS:
            last_month = monthly[-1].month
            horizon_months = [
                month_step(last_month, offset) for offset in range(1, HORIZON_MONTHS + 1)
            ]
            deals = await self._repo.pipeline_deals(
                tenant_id, horizon_months[0], horizon_months[-1]
            )
            pipeline: dict[date, Decimal] = {}
            for deal in deals:
                pipeline[deal.month] = pipeline.get(deal.month, Decimal("0")) + deal.adjusted
            pipeline_value = (
                sum(pipeline.values(), Decimal("0")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                if pipeline
                else Decimal("0")
            )
        else:
            pipeline = {}
        deals_by_month = _deal_list_by_month(deals)

        forecast = compute_forecast(monthly, pipeline=pipeline)
        months = [p.month for p in forecast.points]
        await self._repo.replace_forecast(
            tenant_id,
            forecast.model_version,
            months=months,
            predicted=[p.predicted for p in forecast.points],
            lower_bounds=[p.lower_bound for p in forecast.points],
            upper_bounds=[p.upper_bound for p in forecast.points],
            sigma=forecast.backtest.sigma if forecast.backtest is not None else None,
            backtest_mape=forecast.backtest.mape if forecast.backtest is not None else None,
            pipeline_value=pipeline_value,
            baselines=[p.baseline for p in forecast.points],
            pipeline_uplifts=[p.pipeline for p in forecast.points],
        )
        return RevenueForecastResponse(
            model_version=forecast.model_version,
            backtest_mape=forecast.backtest.mape if forecast.backtest is not None else None,
            sigma=forecast.backtest.sigma if forecast.backtest is not None else None,
            points=[
                ForecastPointResponse(
                    month=p.month,
                    predicted=p.predicted,
                    baseline=p.baseline,
                    pipeline=p.pipeline,
                    lower_bound=p.lower_bound,
                    upper_bound=p.upper_bound,
                    deals=[self._deal_response(deal) for deal in deals_by_month.get(p.month, [])],
                )
                for p in forecast.points
            ],
            history=self._history_response(monthly),
            pipeline_value=pipeline_value,
        )

    async def read(self, tenant_id: uuid.UUID) -> RevenueForecastResponse:
        rows = await self._repo.get_forecast(tenant_id)
        history = self._history_response(
            await self._repo.monthly_revenue(tenant_id, self._history_from_month(date.today()))
        )
        if not rows:
            return RevenueForecastResponse(
                model_version="",
                backtest_mape=None,
                sigma=None,
                points=[],
                history=history,
                pipeline_value=None,
            )
        # The per-deal decomposition is live (computed but not persisted): the
        # stored aggregates are kept as-is, while the deals behind each month's
        # pipeline uplift are re-read so the UI can show them.
        deals_by_month = {}
        if rows:
            deals_by_month = _deal_list_by_month(
                await self._repo.pipeline_deals(tenant_id, rows[0].month, rows[-1].month)
            )
        return RevenueForecastResponse(
            model_version=rows[0].model_version,
            backtest_mape=rows[0].backtest_mape,
            sigma=rows[0].sigma,
            points=[
                ForecastPointResponse(
                    month=row.month,
                    predicted=row.predicted,
                    baseline=row.baseline,
                    pipeline=row.pipeline_uplift,
                    lower_bound=row.lower_bound,
                    upper_bound=row.upper_bound,
                    deals=[self._deal_response(deal) for deal in deals_by_month.get(row.month, [])],
                )
                for row in rows
            ],
            history=history,
            pipeline_value=rows[0].pipeline_value,
        )
