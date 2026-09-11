"""Database access for coaching suggestions (SKY-90).

Owns the CRUD concern for ``ai_coaching_suggestions``. All writes are scoped
by ``tenant_id`` so RLS never sees a cross-tenant leak. The repository is the
ONLY file that touches SQLAlchemy (import-linter contract).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from ai_agent.models.ai_coaching_suggestion import AiCoachingSuggestionModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CoachingSuggestionRepository:
    """Tenant-scoped CRUD for coaching suggestions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_suggestion(
        self,
        *,
        tenant_id: uuid.UUID,
        rep_user_id: uuid.UUID,
        opportunity_id: uuid.UUID | None,
        lead_id: uuid.UUID | None,
        suggestion_type: str,
        title: str,
        body: str,
        evidence: list[dict[str, Any]],
    ) -> uuid.UUID:
        """Persist one coaching suggestion and return its id."""
        row = AiCoachingSuggestionModel(
            tenant_id=tenant_id,
            id=uuid.uuid4(),
            rep_user_id=rep_user_id,
            opportunity_id=opportunity_id,
            lead_id=lead_id,
            suggestion_type=suggestion_type,
            title=title,
            body=body,
            evidence=evidence,
            status="pending",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row.id

    async def list_pending_for_rep(
        self,
        *,
        tenant_id: uuid.UUID,
        rep_user_id: uuid.UUID,
    ) -> list[AiCoachingSuggestionModel]:
        stmt = (
            select(AiCoachingSuggestionModel)
            .where(
                AiCoachingSuggestionModel.tenant_id == tenant_id,
                AiCoachingSuggestionModel.rep_user_id == rep_user_id,
                AiCoachingSuggestionModel.status == "pending",
            )
            .order_by(AiCoachingSuggestionModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_suggestion(
        self,
        *,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
    ) -> AiCoachingSuggestionModel | None:
        stmt = select(AiCoachingSuggestionModel).where(
            AiCoachingSuggestionModel.tenant_id == tenant_id,
            AiCoachingSuggestionModel.id == suggestion_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all_pending(
        self,
        *,
        tenant_id: uuid.UUID,
    ) -> list[AiCoachingSuggestionModel]:
        stmt = (
            select(AiCoachingSuggestionModel)
            .where(
                AiCoachingSuggestionModel.tenant_id == tenant_id,
                AiCoachingSuggestionModel.status == "pending",
            )
            .order_by(AiCoachingSuggestionModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_viewed(
        self,
        *,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
    ) -> None:
        await self._session.execute(
            update(AiCoachingSuggestionModel)
            .where(
                AiCoachingSuggestionModel.tenant_id == tenant_id,
                AiCoachingSuggestionModel.id == suggestion_id,
                AiCoachingSuggestionModel.status == "pending",
            )
            .values(status="viewed")
        )
        await self._session.flush()

    async def mark_reviewed(
        self,
        *,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        status: str,
        reviewed_by: uuid.UUID,
    ) -> None:
        """Mark a suggestion as accepted or dismissed by a manager."""
        now = datetime.now(UTC)
        await self._session.execute(
            update(AiCoachingSuggestionModel)
            .where(
                AiCoachingSuggestionModel.tenant_id == tenant_id,
                AiCoachingSuggestionModel.id == suggestion_id,
            )
            .values(status=status, reviewed_by=reviewed_by, reviewed_at=now)
        )
        await self._session.flush()
