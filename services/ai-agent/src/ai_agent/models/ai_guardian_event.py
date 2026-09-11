"""ai_guardian_events - individual suspicious events (SKY-90).

Each row represents one suspicious event flagged by the Audit Guardian,
linked to its source audit log entry. Events are linked to a weekly report
via ``report_id`` when the report is generated.

``source_table`` identifies the originating audit log table (e.g.
``ai_audit_log``, ``core_audit_log``). ``source_id`` is the originating
row's id. ``evidence`` carries structured context (user, action, IP, etc.)
for the report UI to render.
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


class AiGuardianEventModel(Base):
    """One suspicious event flagged by the Audit Guardian."""

    __tablename__ = "ai_guardian_events"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_ai_guardian_events_severity",
        ),
        Index(
            "idx_guardian_events_tenant_severity",
            "tenant_id",
            "severity",
        ),
        Index(
            "idx_guardian_events_report",
            "tenant_id",
            "report_id",
            postgresql_where=text("report_id IS NOT NULL"),
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
    report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_table: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_action: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    flagged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
