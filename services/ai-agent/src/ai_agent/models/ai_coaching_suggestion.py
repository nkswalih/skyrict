"""ai_coaching_suggestions - per-rep coaching suggestions (SKY-90).

The Sales Coach agent produces actionable coaching suggestions after analyzing
deal activities and call notes. Each suggestion cites specific evidence from
CRM records. Manager-visible only — the role-gated API layer filters by
``erp.crm.read`` + manager role.

``rep_user_id`` references the sales rep being coached (identity user, no FK —
cross-service idiom). ``opportunity_id``/``lead_id`` reference CRM entities
(core tables, no FK — the gateway validated existence before creation).

Status lifecycle: ``pending -> viewed -> accepted | dismissed``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiCoachingSuggestionModel(Base):
    """One AI-generated coaching suggestion for a sales rep."""

    __tablename__ = "ai_coaching_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'viewed', 'accepted', 'dismissed')",
            name="ck_ai_coaching_suggestions_status",
        ),
        CheckConstraint(
            "suggestion_type IN ('follow_up', 'deal_strategy', 'pipeline_review', 'general')",
            name="ck_ai_coaching_suggestions_type",
        ),
        Index(
            "idx_coaching_suggestions_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "idx_coaching_suggestions_rep",
            "tenant_id",
            "rep_user_id",
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
    rep_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    suggestion_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
