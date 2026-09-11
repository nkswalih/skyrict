"""CRM AI orchestration service (SKY-61 Part 11).

Thin facade that wires the deterministic engines (scoring, deal health, follow-up)
to persistence (``CrmAiRepository``) and audit (``AuditService``). The engines
themselves are pure functions; this service handles:

- Loading entity + activity context from core via the gateway.
- Running the deterministic engine.
- Persisting the result row.
- Recording the audit event.

No LLM calls, no network I/O beyond core reads. The service is stateless per
request; it depends on injected gateway and repository instances (keyword-only
constructor, same pattern as ``AnomalyService``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.audit_events import (
    AI_DEAL_HEALTH_ASSESSED,
    AI_FOLLOW_UP_APPLIED,
    AI_FOLLOW_UP_DISMISSED,
    AI_LEAD_SCORED,
)
from ai_agent.features.crm.deal_health import (
    OpportunitySignals,
    assess_deal_health,
)
from ai_agent.features.crm.scoring import score_lead
from ai_agent.models.ai_deal_health import AiDealHealthModel
from ai_agent.models.ai_lead_score import AiLeadScoreModel

if TYPE_CHECKING:
    import uuid

    from ai_agent.core.audit_service import AuditService
    from ai_agent.features.crm.deal_health import DealHealth
    from ai_agent.features.crm.gateway import CrmGatewayPort
    from ai_agent.features.crm.repositories import CrmAiRepository
    from ai_agent.features.crm.scoring import LeadScore
    from ai_agent.models.ai_follow_up_suggestion import AiFollowUpSuggestionModel

logger = structlog.get_logger("ai_agent.crm.service")


@dataclass(frozen=True, slots=True)
class DealHealthSweep:
    """Band counts from one bulk deal-health pass."""

    assessed: int
    healthy: int
    at_risk: int
    critical: int


class CrmAiService:
    """Orchestration layer for CRM AI operations (keyword-only constructor)."""

    def __init__(
        self,
        *,
        gateway: CrmGatewayPort,
        repo: CrmAiRepository,
        audit: AuditService,
    ) -> None:
        self._gateway = gateway
        self._repo = repo
        self._audit = audit

    # --- lead scoring --------------------------------------------------------

    async def compute_lead_score(
        self,
        *,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> LeadScore:
        """Compute, persist, and audit a lead score for the given lead.

        Returns the deterministic score result for immediate display.
        """
        lead = await self._gateway.get_lead(lead_id=lead_id)
        activities = await self._gateway.list_activities_for_entity(
            entity_type="lead", entity_id=lead_id
        )
        now = datetime.now(UTC)
        result = score_lead(lead=lead, activities=activities, now=now)

        row = AiLeadScoreModel(
            tenant_id=tenant_id,
            lead_id=lead_id,
            score=result.score,
            confidence=result.confidence,
            factors=result.factors,
        )
        await self._repo.save_lead_score(row)

        await self._audit.log(
            action=AI_LEAD_SCORED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"lead_id": str(lead_id)},
            output_payload={
                "score": result.score,
                "confidence": result.confidence,
            },
        )

        return result

    # --- deal health ---------------------------------------------------------

    async def compute_deal_health(
        self,
        *,
        tenant_id: uuid.UUID,
        opportunity_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DealHealth:
        """Compute, persist, and audit deal health for the given opportunity."""
        opp = await self._gateway.get_opportunity(opportunity_id=opportunity_id)
        activities = await self._gateway.list_activities_for_entity(
            entity_type="opportunity", entity_id=opportunity_id
        )
        now = datetime.now(UTC)

        signals = OpportunitySignals(
            opportunity_id=opportunity_id,
            stage=opp.stage,
            probability=opp.probability,
            has_amount=opp.has_amount,
            created_at=opp.created_at,
            last_stage_change_at=opp.last_stage_change_at,
            expected_close_date=opp.expected_close_date,
        )
        result = assess_deal_health(signals=signals, activities=activities, now=now)

        row = AiDealHealthModel(
            tenant_id=tenant_id,
            opportunity_id=opportunity_id,
            health=result.health,
            confidence=result.confidence,
            risk_factors=result.risk_factors,
            recommended_actions=result.recommended_actions,
        )
        await self._repo.save_deal_health(row)

        await self._audit.log(
            action=AI_DEAL_HEALTH_ASSESSED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"opportunity_id": str(opportunity_id)},
            output_payload={
                "health": result.health,
                "confidence": result.confidence,
                "risk_count": len(result.risk_factors),
            },
        )

        return result

    async def sweep_deal_health(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        horizon_days: int = 365,
    ) -> DealHealthSweep:
        """Compute + persist health for every open opportunity expected to close
        within the next ``horizon_days`` (the forecast-card horizon)."""
        now = datetime.now(UTC)
        today = now.date()
        horizon_end = (now + timedelta(days=horizon_days)).date()
        counts = {"assessed": 0, "green": 0, "yellow": 0, "red": 0}
        for opp in await self._gateway.list_opportunities():
            if opp.expected_close_date is None:
                continue
            if not today <= opp.expected_close_date <= horizon_end:
                continue
            result = await self.compute_deal_health(
                tenant_id=tenant_id,
                opportunity_id=opp.id,
                user_id=user_id,
            )
            counts["assessed"] += 1
            counts[result.health] += 1
        return DealHealthSweep(
            assessed=counts["assessed"],
            healthy=counts["green"],
            at_risk=counts["yellow"],
            critical=counts["red"],
        )

    # --- follow-up management ------------------------------------------------

    async def list_pending_follow_ups(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[AiFollowUpSuggestionModel]:
        """List pending follow-up suggestions for the authenticated user."""
        return await self._repo.list_pending_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
        )

    async def apply_follow_up(
        self,
        *,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        user_id: uuid.UUID,
        activity_id: uuid.UUID,
    ) -> AiFollowUpSuggestionModel:
        """Apply a pending follow-up suggestion (one-click send).

        Marks the suggestion as ``sent`` and records the created CRM activity
        ID for the audit trail. The caller is responsible for actually creating
        the CRM activity in core - this method only transitions the suggestion
        status.
        """
        row = await self._repo.get_for_apply(
            tenant_id=tenant_id,
            suggestion_id=suggestion_id,
        )
        if row is None:
            raise ValueError("follow-up suggestion not found")
        if row.status != "pending":
            raise ValueError(f"follow-up suggestion is already {row.status}")
        if row.user_id != user_id:
            raise ValueError("follow-up suggestion belongs to another user")

        await self._repo.mark_applied(
            row=row,
            applied_by=user_id,
            activity_id=activity_id,
        )

        await self._audit.log(
            action=AI_FOLLOW_UP_APPLIED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={
                "suggestion_id": str(suggestion_id),
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id),
            },
            output_payload={"activity_id": str(activity_id)},
        )

        return row

    async def dismiss_follow_up(
        self,
        *,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AiFollowUpSuggestionModel:
        """Dismiss a pending follow-up suggestion."""
        row = await self._repo.get_for_apply(
            tenant_id=tenant_id,
            suggestion_id=suggestion_id,
        )
        if row is None:
            raise ValueError("follow-up suggestion not found")
        if row.status != "pending":
            raise ValueError(f"follow-up suggestion is already {row.status}")
        if row.user_id != user_id:
            raise ValueError("follow-up suggestion belongs to another user")

        await self._repo.mark_dismissed(row=row)

        await self._audit.log(
            action=AI_FOLLOW_UP_DISMISSED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={
                "suggestion_id": str(suggestion_id),
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id),
            },
        )

        return row
