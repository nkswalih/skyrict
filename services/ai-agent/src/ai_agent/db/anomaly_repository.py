"""Tenant-scoped access to ai_anomalies (spec §4.7).

Detection inserts (deduped against OPEN rows of the same type+product);
review applies open -> resolved | dismissed | escalated transitions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select, update

from ai_agent.models.ai_anomaly import AiAnomalyModel
from skyrict_common.exceptions import NotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AnomalyRepository:
    """Persistence for detected stock anomalies."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        anomaly_type: str,
        severity: str,
        title: str,
        description: str,
        affected_product_id: uuid.UUID | None = None,
        affected_warehouse_id: uuid.UUID | None = None,
        related_movement_ids: list[uuid.UUID] | None = None,
    ) -> AiAnomalyModel:
        """Insert one OPEN anomaly row."""
        row = AiAnomalyModel(
            tenant_id=tenant_id,
            id=uuid.uuid4(),
            anomaly_type=anomaly_type,
            severity=severity,
            title=title,
            description=description,
            affected_product_id=affected_product_id,
            affected_warehouse_id=affected_warehouse_id,
            related_movement_ids=related_movement_ids or [],
            status="open",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def has_open(
        self,
        *,
        tenant_id: uuid.UUID,
        anomaly_type: str,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> bool:
        """True when an OPEN anomaly of this type+scope exists (dedupe gate)."""
        conditions = [
            AiAnomalyModel.tenant_id == tenant_id,
            AiAnomalyModel.anomaly_type == anomaly_type,
            AiAnomalyModel.status == "open",
        ]
        if product_id is not None:
            conditions.append(AiAnomalyModel.affected_product_id == product_id)
        if warehouse_id is not None:
            conditions.append(AiAnomalyModel.affected_warehouse_id == warehouse_id)
        result = await self.session.execute(
            select(func.count()).select_from(AiAnomalyModel).where(*conditions)
        )
        return int(result.scalar_one()) > 0

    async def list_all(
        self, *, tenant_id: uuid.UUID, status: str | None = None, limit: int = 100
    ) -> tuple[list[AiAnomalyModel], dict[str, int]]:
        """Status-filtered feed plus meta counts (total/open/high_severity)."""
        base = select(AiAnomalyModel).where(AiAnomalyModel.tenant_id == tenant_id)
        if status is not None:
            base = base.where(AiAnomalyModel.status == status)
        total_result = await self.session.execute(select(func.count()).select_from(base.subquery()))
        rows_result = await self.session.execute(
            base.order_by(desc(AiAnomalyModel.created_at)).limit(limit)
        )
        rows = list(rows_result.scalars().all())

        all_open = await self.session.execute(
            select(func.count())
            .select_from(AiAnomalyModel)
            .where(
                AiAnomalyModel.tenant_id == tenant_id,
                AiAnomalyModel.status == "open",
            )
        )
        high_open = await self.session.execute(
            select(func.count())
            .select_from(AiAnomalyModel)
            .where(
                AiAnomalyModel.tenant_id == tenant_id,
                AiAnomalyModel.status == "open",
                AiAnomalyModel.severity.in_(("high", "critical")),
            )
        )
        meta = {
            "total": int(total_result.scalar_one()),
            "open": int(all_open.scalar_one()),
            "high_severity": int(high_open.scalar_one()),
        }
        return rows, meta

    async def get(self, *, tenant_id: uuid.UUID, anomaly_id: uuid.UUID) -> AiAnomalyModel:
        """Fetch one row; 404 when absent or mis-scoped."""
        result = await self.session.execute(
            select(AiAnomalyModel).where(
                AiAnomalyModel.tenant_id == tenant_id,
                AiAnomalyModel.id == anomaly_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Anomaly not found")
        return row

    async def record_review(
        self,
        *,
        row: AiAnomalyModel,
        status: str,
        reviewed_by: uuid.UUID,
        resolution_note: str | None,
    ) -> AiAnomalyModel:
        """Apply a review transition (caller validated the source status)."""
        row.status = status
        row.reviewed_by = reviewed_by
        row.reviewed_at = datetime.now(tz=UTC)
        row.resolution_note = resolution_note
        await self.session.flush()
        return row

    async def auto_close_stale(self, *, close_days: int) -> int:
        """Bulk-dismiss open anomalies older than *close_days* (spec 4.4).

        Returns the number of rows affected.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(days=close_days)
        result = await self.session.execute(
            update(AiAnomalyModel)
            .where(
                AiAnomalyModel.status == "open",
                AiAnomalyModel.created_at < cutoff,
            )
            .values(
                status="dismissed",
                resolution_note="Auto-closed after configured expiry period.",
            )
        )
        await self.session.flush()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
