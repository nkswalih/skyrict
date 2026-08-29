"""ai_hr_quality_scores — per-employee data-quality score (8.1.3).

Written by the weekly (lazy-on-read TTL) quality recalc; read for the org KPI
(L1) and the per-employee drill-down (L2, ``erp.hr.ai.individual``). Sub-scores
carry the documented weights: mandatory 0.50, contact 0.25, document 0.25.
``issues`` is the human-readable list of failing signals per employee.
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
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class QualityGrade:
    """Grades for ``ai_hr_quality_scores.grade`` (A=>=0.9 ... F=<0.5)."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class QualityScoreModel(Base):
    """One quality scoring run's result for a single employee."""

    __tablename__ = "ai_hr_quality_scores"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["erp_employees.tenant_id", "erp_employees.id"],
            name="fk_ai_hr_quality_scores_employee",
        ),
        CheckConstraint(
            "grade IN ('A', 'B', 'C', 'D', 'F')",
            name="ck_ai_hr_quality_scores_grade",
        ),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            "generated_at",
            name="uq_ai_hr_quality_scores_employee_run",
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
    score: Mapped[object] = mapped_column(Numeric(5, 4), nullable=False)
    grade: Mapped[str] = mapped_column(String(4), nullable=False)
    mandatory_score: Mapped[object] = mapped_column(Numeric(5, 4), nullable=False)
    contact_score: Mapped[object] = mapped_column(Numeric(5, 4), nullable=False)
    document_score: Mapped[object] = mapped_column(Numeric(5, 4), nullable=False)
    issues: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
