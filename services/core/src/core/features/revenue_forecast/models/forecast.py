"""erp_revenue_forecast - one persisted row per (tenant, forecast month).

Forecasts are a computed product produced by the revenue-forecast feature
(SKY-82 A4). ``UNIQUE (tenant_id, month)`` is the recompute guard: refreshing
upserts, a second row for the same month is a programming error. The band is
the ±1.5 sigma historical-error interval from the backtest; ``backtest_mape`` and
``sigma`` are NULL when history is too short to validate.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class ErpRevenueForecastModel(Base):
    __tablename__ = "erp_revenue_forecast"
    __table_args__ = (
        UniqueConstraint("tenant_id", "month", name="uq_erp_revenue_forecast_tenant_month"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    predicted: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    sigma: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    backtest_mape: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    # Run-level total weighted expected pipeline (probability/100 x amount of
    # open CRM deals) blended into this horizon; NULL when the forecast abstained
    # or the model ran before pipeline weighting existed.
    pipeline_value: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    # Per-month decomposition of ``predicted``: the trend + seasonal baseline
    # and the CRM pipeline uplift blended in (predicted == baseline + uplift).
    # NULL on rows persisted before migration 0047 (predates decomposition).
    baseline: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    pipeline_uplift: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    model_version: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'sma-6'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
