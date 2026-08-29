"""ai_hr_public_holidays — the per-tenant public-holiday calendar (8.2.1).

Input data for the ``pre_holiday_spike`` leave-pattern anomaly, so the detector
can tell "leave adjacent to a public holiday" apart from ordinary long
weekends. Tenant-scoped config (like ``erp_leave_types``): every tenant owns
its own holiday rows. ``department_id`` NULL means the holiday is org-wide; a
row stamped to one department lets a specific team shadow an org date (both
rows may coexist — the unique key is ``(tenant, department, date)``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class AiHrPublicHolidayModel(Base):
    """One public-holiday/office-closure day within a tenant."""

    __tablename__ = "ai_hr_public_holidays"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["erp_departments.tenant_id", "erp_departments.id"],
            name="fk_ai_hr_public_holidays_department",
        ),
        UniqueConstraint(
            "tenant_id",
            "department_id",
            "calendar_date",
            name="uq_ai_hr_public_holidays_dept_date",
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
    calendar_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
