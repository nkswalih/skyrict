"""ai_abc_classifications - per-SKU ABC band assignments (SKY-68).

Pareto classification: A=80% revenue, B=next 15%, C=remaining 5%.
Recalculated weekly via background job.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiAbcClassificationModel(Base):
    __tablename__ = "ai_abc_classifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["erp_products.tenant_id", "erp_products.id"],
            ondelete="CASCADE",
            name="fk_ai_abc_product_tenant",
        ),
        UniqueConstraint("tenant_id", "product_id", name="uq_ai_abc_product"),
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
    band: Mapped[str] = mapped_column(String(1), nullable=False, server_default=text("'C'"))
    revenue_share: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=False, server_default=text("0")
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
