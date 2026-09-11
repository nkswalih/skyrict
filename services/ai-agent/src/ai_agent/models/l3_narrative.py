"""ai_l3_narrative_snapshots - cached L3 HR/Payroll narrator narratives.

One row per narrated narrative generation. ``status`` is ``generated`` when an
LLM produced a narrative, ``abstained`` when the narrator deliberately declined.
``figures`` stores the token→figure mapping for render substitution.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiL3NarrativeModel(Base):
    """One L3 narrative snapshot for a tenant/kind/date."""

    __tablename__ = "ai_l3_narrative_snapshots"
    __table_args__ = (
        Index(
            "idx_ai_l3_narratives_tenant_kind_as_of",
            "tenant_id",
            "kind",
            "as_of",
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
    kind: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'generated'")
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    caveat: Mapped[str | None] = mapped_column(Text, nullable=True)
    figures: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
