"""ai_hr_leave_suggestions — smart leave-window suggestions (8.2.4).

Written by the suggestion engine (deterministic, non-LLM); exposed to the
employee's own leave application flow via the self-scoped ``/portal`` surface
(gated by ``erp.leave.self``, NOT ``erp.hr.ai.individual``). Suggestions NEVER
auto-submit: they appear as chips that one-click **prefill** the leave form.
``status`` is ``pending|used|dismissed`` where ``used`` records a prefill
selection, not an approved request.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
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


class LeaveSuggestionStatus:
    PENDING = "pending"
    USED = "used"
    DISMISSED = "dismissed"


class LeaveSuggestionModel(Base):
    __tablename__ = "ai_hr_leave_suggestions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["erp_employees.tenant_id", "erp_employees.id"],
            name="fk_ai_hr_leave_suggestions_employee",
        ),
        CheckConstraint(
            "status IN ('pending', 'used', 'dismissed')",
            name="ck_ai_hr_leave_suggestions_status",
        ),
        CheckConstraint("days > 0", name="ck_ai_hr_leave_suggestions_days_positive"),
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
    leave_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pending")
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
