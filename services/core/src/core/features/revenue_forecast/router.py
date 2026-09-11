"""Revenue-forecast API routes - thin wrappers over :class:`RevenueForecastService`.

Authorization reuses the finance permission keys (``erp.finance.read`` for
reads, ``erp.finance.write`` for the recompute mutation). ``GET`` serves the
stored forecast (weekly recompute / manual refresh keep it fresh); ``POST
/revenue/refresh`` recomputes from approved-invoice history and upserts.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from core.api.deps import get_revenue_forecast_service
from core.features.finance.router import require_finance_read, require_finance_write
from core.features.revenue_forecast.schemas import (
    RevenueForecastEnvelope,
    RevenueForecastResponse,
)
from core.features.revenue_forecast.service import RevenueForecastService

router = APIRouter(prefix="/finance/forecast", tags=["finance.forecast"])


def _tenant_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["tenant_id"]
    return val if isinstance(val, uuid.UUID) else uuid.UUID(val)


@router.get("/revenue", response_model=RevenueForecastEnvelope)
async def get_revenue_forecast(
    current_user: dict[str, Any] = Depends(require_finance_read),
    svc: RevenueForecastService = Depends(get_revenue_forecast_service),
) -> RevenueForecastEnvelope:
    forecast = await svc.read(_tenant_id(current_user))
    return RevenueForecastEnvelope(data=forecast)


@router.post("/revenue/refresh", response_model=RevenueForecastEnvelope)
async def refresh_revenue_forecast(
    current_user: dict[str, Any] = Depends(require_finance_write),
    svc: RevenueForecastService = Depends(get_revenue_forecast_service),
) -> RevenueForecastEnvelope:
    forecast: RevenueForecastResponse = await svc.refresh(_tenant_id(current_user))
    return RevenueForecastEnvelope(data=forecast)
