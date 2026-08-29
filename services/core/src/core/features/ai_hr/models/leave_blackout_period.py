"""ai_hr_leave_blackout_periods — times the suggestion engine must avoid (8.2.4).

Tenant-scoped config the smart leave-window suggestion engine treats as hard
constraints: a candidate window overlapping an active blackout for the
employee's department is deprioritized/shifted, and the why-suggested reasons
call the overlap out explicitly. ``department_id`` NULL = org-wide blackout;
a row stamped to one department only affects that department's suggestions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class AiHrLeaveBlackoutPeriodModel(Base):
    """One contiguous leave-blackout window within a tenant."""

    __tablename__ = "ai_hr_leave_blackout_periods"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["erp_departments.tenant_id", "erp_departments.id"],
            name="fk_ai_hr_leave_blackout_periods_department",
        ),
        CheckConstraint(
            "end_date >= start_date",
            name="ck_ai_hr_leave_blackout_periods_range",
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
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
