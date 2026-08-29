"""ai_hr_utilization_alerts — forfeit-risk / negative-accrual findings (8.1.4).

Written by the utilization scan; exposed via the HR-facing
``/ai/hr/alerts/utilization`` feed (L1 aggregate / L2 per-employee under
``erp.hr.ai.individual``) and the self-scoped ``/portal/leave/alerts`` feed so
an employee can see their own forfeit warning. ``forfeit_risk`` carries the
projected days that would be lost at year end within the default 60-day
forfeit window.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class UtilizationAlertType:
    FORFEIT_RISK = "forfeit_risk"
    NEGATIVE_ACCRUAL = "negative_accrual"


class UtilizationAlertStatus:
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class UtilizationAlertModel(Base):
    __tablename__ = "ai_hr_utilization_alerts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["erp_employees.tenant_id", "erp_employees.id"],
            name="fk_ai_hr_utilization_alerts_employee",
        ),
        CheckConstraint(
            "alert_type IN ('forfeit_risk', 'negative_accrual')",
            name="ck_ai_hr_utilization_alerts_type",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_hr_utilization_alerts_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'dismissed', 'resolved')",
            name="ck_ai_hr_utilization_alerts_status",
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
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(24), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    balance_days: Mapped[int] = mapped_column(Integer, nullable=False)
    projected_forfeiture_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days_remaining_in_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(14), nullable=False, server_default="open")
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
