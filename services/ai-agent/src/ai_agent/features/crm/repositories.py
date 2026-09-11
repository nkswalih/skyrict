"""Database access for the CRM AI tables (SKY-61 Part 11 storage).

Owns the three tenant-scoped CRUD concerns for ``ai_lead_scores``,
``ai_deal_health``, and ``ai_follow_up_suggestions``. All writes are scoped by
``tenant_id`` so RLS never sees a cross-tenant leak. The follow-up repository
also implements the status lifecycle (pending -> sent|dismissed|expired) and
the expiry sweep the hourly check consumes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select, update

from ai_agent.models.ai_deal_health import AiDealHealthModel
from ai_agent.models.ai_follow_up_suggestion import AiFollowUpSuggestionModel
from ai_agent.models.ai_lead_score import AiLeadScoreModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class CrmAiRepository:
    """Combined repository over the three CRM AI tables (one session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- lead scores ---------------------------------------------------------
    async def latest_lead_score(
        self, *, tenant_id: uuid.UUID, lead_id: uuid.UUID
    ) -> AiLeadScoreModel | None:
        stmt = (
            select(AiLeadScoreModel)
            .where(
                AiLeadScoreModel.tenant_id == tenant_id,
                AiLeadScoreModel.lead_id == lead_id,
            )
            .order_by(AiLeadScoreModel.computed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_lead_score(self, row: AiLeadScoreModel) -> None:
        self._session.add(row)

    # --- deal health ---------------------------------------------------------
    async def latest_deal_health(
        self, *, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
    ) -> AiDealHealthModel | None:
        stmt = (
            select(AiDealHealthModel)
            .where(
                AiDealHealthModel.tenant_id == tenant_id,
                AiDealHealthModel.opportunity_id == opportunity_id,
            )
            .order_by(AiDealHealthModel.computed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_deal_health(self, row: AiDealHealthModel) -> None:
        self._session.add(row)

    async def save_deal_health_assessment(
        self,
        *,
        tenant_id: uuid.UUID,
        opportunity_id: uuid.UUID,
        health: str,
        confidence: float,
        risk_factors: list[str],
        recommended_actions: list[str],
    ) -> None:
        """Persist one scheduled/engine assessment (owns the ORM model, so the
        API layer never imports ``ai_agent.models`` directly)."""
        self._session.add(
            AiDealHealthModel(
                tenant_id=tenant_id,
                opportunity_id=opportunity_id,
                health=health,
                confidence=confidence,
                risk_factors=risk_factors,
                recommended_actions=recommended_actions,
            )
        )

    # --- follow-up suggestions -----------------------------------------------
    async def list_pending_for_user(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[AiFollowUpSuggestionModel]:
        stmt = (
            select(AiFollowUpSuggestionModel)
            .where(
                AiFollowUpSuggestionModel.tenant_id == tenant_id,
                AiFollowUpSuggestionModel.user_id == user_id,
                AiFollowUpSuggestionModel.status == "pending",
            )
            .order_by(AiFollowUpSuggestionModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_apply(
        self, *, tenant_id: uuid.UUID, suggestion_id: uuid.UUID
    ) -> AiFollowUpSuggestionModel | None:
        stmt = select(AiFollowUpSuggestionModel).where(
            AiFollowUpSuggestionModel.tenant_id == tenant_id,
            AiFollowUpSuggestionModel.id == suggestion_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_follow_up(self, row: AiFollowUpSuggestionModel) -> None:
        self._session.add(row)

    async def mark_applied(
        self,
        *,
        row: AiFollowUpSuggestionModel,
        applied_by: uuid.UUID,
        activity_id: uuid.UUID,
    ) -> None:
        row.status = "sent"
        row.sent_at = datetime.now(UTC)
        row.applied_by = applied_by
        row.activity_id = activity_id
        await self._session.flush()

    async def mark_dismissed(self, *, row: AiFollowUpSuggestionModel) -> None:
        row.status = "dismissed"
        await self._session.flush()

    async def expire_stale(self, *, tenant_id: uuid.UUID, now: datetime | None = None) -> int:
        """Mark pending suggestions past expires_at as expired. Returns count."""
        stamp = now or datetime.now(UTC)
        result = await self._session.execute(
            update(AiFollowUpSuggestionModel)
            .where(
                AiFollowUpSuggestionModel.tenant_id == tenant_id,
                AiFollowUpSuggestionModel.status == "pending",
                AiFollowUpSuggestionModel.expires_at < stamp,
            )
            .values(status="expired")
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def delete_follow_ups_for_entity(
        self, *, tenant_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> None:
        """Remove generated suggestions when an entity is deleted (soft-link hygiene)."""
        await self._session.execute(
            delete(AiFollowUpSuggestionModel).where(
                AiFollowUpSuggestionModel.tenant_id == tenant_id,
                AiFollowUpSuggestionModel.entity_type == entity_type,
                AiFollowUpSuggestionModel.entity_id == entity_id,
            )
        )

    async def pending_count_for_entity(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> int:
        """Count pending suggestions for one entity (dedup guard for the scan)."""
        stmt = (
            select(func.count())
            .select_from(AiFollowUpSuggestionModel)
            .where(
                AiFollowUpSuggestionModel.tenant_id == tenant_id,
                AiFollowUpSuggestionModel.entity_type == entity_type,
                AiFollowUpSuggestionModel.entity_id == entity_id,
                AiFollowUpSuggestionModel.status == "pending",
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def create_follow_up_suggestion(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        suggestion_type: str,
        draft_content: str,
        reasoning: str,
        confidence: float,
        stale_days: int,
    ) -> AiFollowUpSuggestionModel:
        """Create and persist a new pending follow-up suggestion.

        The ``stale_days`` value is used to set ``expires_at`` to 7 days from
        now (the application-set expiry convention documented in the model).
        """
        row = AiFollowUpSuggestionModel(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            suggestion_type=suggestion_type,
            draft_content=draft_content,
            reasoning=reasoning,
            confidence=confidence,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        self._session.add(row)
        await self._session.flush()
        return row
