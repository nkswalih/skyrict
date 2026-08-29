"""Tenant-scoped access to ai_suggestions (spec §3.6).

Creation is bulk (one scan produces many rows); review is single-row
state transition (pending -> approved | rejected) recording who/when/why.
The partial unique index ``idx_ai_suggestions_pending_unique`` enforces
"one pending suggestion per product+warehouse" at the DATABASE level -
``create_pending`` relies on it and surfaces violations as ConflictError.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select, update

from ai_agent.models.ai_suggestion import AiSuggestionModel
from skyrict_common.exceptions import NotFoundError

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession


class SuggestionRepository:
    """Persistence for restock suggestions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_pending(
        self,
        *,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        current_stock: Decimal,
        reorder_point: Decimal,
        suggested_qty: Decimal,
        estimated_cost: Decimal | None,
        reason: str,
        confidence: Decimal | None,
    ) -> AiSuggestionModel:
        """Insert one pending suggestion; flush exposes unique-index races."""
        row = AiSuggestionModel(
            tenant_id=tenant_id,
            id=uuid.uuid4(),
            product_id=product_id,
            warehouse_id=warehouse_id,
            current_stock=current_stock,
            reorder_point=reorder_point,
            suggested_qty=suggested_qty,
            estimated_cost=estimated_cost,
            reason=reason,
            confidence=confidence,
            status="pending",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_by_status(
        self, *, tenant_id: uuid.UUID, status: str = "pending", limit: int = 100
    ) -> tuple[list[AiSuggestionModel], int]:
        """Status-filtered rows (newest first) plus total count for meta."""
        base = select(AiSuggestionModel).where(
            AiSuggestionModel.tenant_id == tenant_id,
            AiSuggestionModel.status == status,
        )
        total_result = await self.session.execute(select(func.count()).select_from(base.subquery()))
        total = int(total_result.scalar_one())
        rows_result = await self.session.execute(
            base.order_by(desc(AiSuggestionModel.created_at)).limit(limit)
        )
        return list(rows_result.scalars().all()), total

    async def get_for_review(
        self, *, tenant_id: uuid.UUID, suggestion_id: uuid.UUID
    ) -> AiSuggestionModel:
        """Fetch one row for a review decision; 404 when absent/mis-scoped."""
        result = await self.session.execute(
            select(AiSuggestionModel).where(
                AiSuggestionModel.tenant_id == tenant_id,
                AiSuggestionModel.id == suggestion_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Suggestion not found")
        return row

    async def record_review(
        self,
        *,
        row: AiSuggestionModel,
        status: str,
        reviewed_by: uuid.UUID,
        review_note: str | None,
    ) -> AiSuggestionModel:
        """Apply a review decision (caller validated the transition)."""
        row.status = status
        row.reviewed_by = reviewed_by
        row.reviewed_at = _utcnow()
        row.review_note = review_note
        await self.session.flush()
        return row

    async def expire_stale(self, *, expiry_days: int) -> int:
        """Bulk-expire pending suggestions older than *expiry_days* (spec 3.4).

        Returns the number of rows affected.
        """
        cutoff = _utcnow() - timedelta(days=expiry_days)
        result = await self.session.execute(
            update(AiSuggestionModel)
            .where(
                AiSuggestionModel.status == "pending",
                AiSuggestionModel.created_at < cutoff,
            )
            .values(status="expired")
        )
        await self.session.flush()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _utcnow() -> datetime:
    """Aware-UTC now."""
    return datetime.now(tz=UTC)
