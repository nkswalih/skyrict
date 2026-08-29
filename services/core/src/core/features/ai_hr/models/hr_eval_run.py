"""hr_eval_runs — model eval-harness precision results (HR-AI-002).

Each row records one metric (e.g. ``attrition_precision``,
``leave_anomaly_precision``) evaluated over labeled seed cases by the ai-agent
eval harness. ``threshold`` / ``met_threshold`` record whether the documented
minimum precision was met so the eval can *warn* rather than fail.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class HrEvalRunModel(Base):
    __tablename__ = "hr_eval_runs"
    __table_args__ = ()

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    precision: Mapped[object] = mapped_column(Numeric(5, 4), nullable=False)
    considered: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[object | None] = mapped_column(Numeric(5, 4), nullable=True)
    met_threshold: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
