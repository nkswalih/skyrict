"""ai_forecasts - per-SKU demand forecast cache (SKY-68).

Stores computed forecast results for each product at 4/8/12 week horizons.
Refreshed by the forecast service on demand or via background recalc.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiForecastModel(Base):
    __tablename__ = "ai_forecasts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["erp_products.tenant_id", "erp_products.id"],
            ondelete="CASCADE",
            name="fk_ai_forecasts_product_tenant",
        ),
        UniqueConstraint(
            "tenant_id", "product_id", "horizon_weeks", name="uq_ai_forecast_product_horizon"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    horizon_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_daily_demand: Mapped[float] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )
    weeks_of_supply: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    stockout_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
