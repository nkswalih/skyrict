"""Response schemas for the revenue-forecast feature (SKY-82 A4).

The forecast is a computed product - one point per forecast month, each with
an optional ±1.5 sigma confidence band. ``backtest_mape`` / ``sigma`` are
run-level aggregates; both are None when history is too short to validate.
``pipeline_value`` is the run-level total of weighted expected pipeline
(open CRM opportunities, ``probability/100 x amount`` bucketed by expected
close month) blended into the horizon; None when the forecast abstained.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from skyrict_common.schemas import ResponseEnvelope


class ForecastDealResponse(BaseModel):
    """One open CRM deal blended into a forecast month (SKY-82 deal health).

    ``weighted`` is the raw conversion value (``probability/100 x amount``);
    ``adjusted`` applies the deal's latest ai-agent health rating - green
    keeps full weight, yellow/red discount it (``factor``), blended toward
    neutral by ``confidence``. ``health`` / ``confidence`` are None for deals
    the health engine has never assessed (``factor`` 1.0). The month's
    ``pipeline`` is the sum of its deals' ``adjusted`` values.
    """

    id: uuid.UUID
    name: str
    amount: Decimal | None
    probability: int
    expected_close_date: date
    weighted: Decimal
    health: str | None = None
    confidence: float | None = None
    factor: Decimal
    adjusted: Decimal


class ForecastPointResponse(BaseModel):
    month: date
    predicted: Decimal
    # Per-month decomposition: the trend + seasonal baseline and the CRM
    # pipeline uplift blended in (predicted == baseline + pipeline).
    baseline: Decimal | None = None
    pipeline: Decimal | None = None
    lower_bound: Decimal | None
    upper_bound: Decimal | None
    # The per-deal detail behind ``pipeline`` - which deals close this month
    # and at what health-adjusted value. Empty when the forecast abstained.
    deals: list[ForecastDealResponse] = Field(default_factory=list)


class ActualPointResponse(BaseModel):
    month: date
    actual: Decimal


class RevenueForecastResponse(BaseModel):
    model_version: str
    backtest_mape: Decimal | None
    sigma: Decimal | None
    points: list[ForecastPointResponse]
    history: list[ActualPointResponse] = Field(default_factory=list)
    pipeline_value: Decimal | None = None


RevenueForecastEnvelope = ResponseEnvelope[RevenueForecastResponse]
