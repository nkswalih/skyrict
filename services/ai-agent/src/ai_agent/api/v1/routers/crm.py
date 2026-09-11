"""CRM AI endpoints - lead score badge, deal health badge, follow-up management (SKY-61).

Routes mount at ``/api/v1/ai/crm`` and expose the deterministic engines built
in C4-C7. The gateway is bound to the *caller's* JWT so core enforces the
existing CRM read permissions - the AI service never bypasses authorization.

Rate limits (C8):
- ``/score``, ``/health`` and ``/opportunities/sweep`` use ``RATE_LIMIT_CRM_PER_MIN`` (15/min/user).
- ``/follow-ups/{id}/apply`` and ``/dismiss`` use ``RATE_LIMIT_CRM_APPLY_PER_MIN`` (10/min/user).
- Both enforce the aggregate ``RATE_LIMIT_TENANT_PER_MIN`` (100/min/tenant).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.api.v1.schemas.crm_ai import (
    DealHealthResponse,
    DealHealthSweepResponse,
    FollowUpItem,
    FollowUpSuggestionType,
    HealthBand,
    LeadScoreResponse,
)
from ai_agent.core.audit_service import AuditService
from ai_agent.core.config import settings
from ai_agent.core.rate_limit import limiter
from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.audit_repository import AiAuditLogRepository
from ai_agent.features.crm.gateway import HttpCrmGateway
from ai_agent.features.crm.repositories import CrmAiRepository
from ai_agent.features.crm.service import CrmAiService

router = APIRouter(prefix="/ai/crm", tags=["ai-crm"])


def _follow_up_to_item(row: Any) -> FollowUpItem:
    """Map a repository row to the API response schema."""
    return FollowUpItem(
        id=row.id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        suggestion_type=FollowUpSuggestionType(row.suggestion_type),
        draft_content=row.draft_content,
        reasoning=row.reasoning,
        confidence=row.confidence,
        status=row.status,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------


def _get_crm_gateway(request: Request) -> HttpCrmGateway:
    """CRM gateway bound to THIS request's identity - never service credentials."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    return HttpCrmGateway(
        base_url=str(settings.INVENTORY_SERVICE_URL),
        bearer_token=token,
        tenant_slug=TenantContext.get_tenant_slug() or "",
    )


def _build_service(request: Request, session: AsyncSession) -> CrmAiService:
    """Compose the CRM AI stack for one request."""
    return CrmAiService(
        gateway=_get_crm_gateway(request),
        repo=CrmAiRepository(session),
        audit=AuditService(AiAuditLogRepository(session)),
    )


def get_crm_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CrmAiService:
    """FastAPI dependency wrapping :func:`_build_service`."""
    return _build_service(request, session)


# ---------------------------------------------------------------------------
# Lead score
# ---------------------------------------------------------------------------


@router.post(
    "/leads/{lead_id}/score",
    response_model=LeadScoreResponse,
)
async def score_lead(
    lead_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[CrmAiService, Depends(get_crm_service)],
) -> LeadScoreResponse:
    """Compute and persist a deterministic AI score for the given lead."""
    await limiter.enforce(
        key=f"ai:crm:{user['tenant_id']}:{user['user_id']}",
        limit=settings.RATE_LIMIT_CRM_PER_MIN,
        window_seconds=60,
    )
    await limiter.enforce(
        key=f"ai:tenant_total:{user['tenant_id']}",
        limit=settings.RATE_LIMIT_TENANT_PER_MIN,
        window_seconds=60,
    )
    result = await service.compute_lead_score(
        tenant_id=user["tenant_id"],
        lead_id=lead_id,
        user_id=user["user_id"],
    )
    return LeadScoreResponse(
        lead_id=lead_id,
        score=result.score,
        confidence=result.confidence,
        factors=result.factors,
        model_version="v1",
        computed_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Deal health
# ---------------------------------------------------------------------------


@router.get(
    "/opportunities/{opportunity_id}/health",
    response_model=DealHealthResponse,
)
async def get_deal_health(
    opportunity_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[CrmAiService, Depends(get_crm_service)],
) -> DealHealthResponse:
    """Compute and persist a deterministic health assessment for the given opportunity."""
    await limiter.enforce(
        key=f"ai:crm:{user['tenant_id']}:{user['user_id']}",
        limit=settings.RATE_LIMIT_CRM_PER_MIN,
        window_seconds=60,
    )
    await limiter.enforce(
        key=f"ai:tenant_total:{user['tenant_id']}",
        limit=settings.RATE_LIMIT_TENANT_PER_MIN,
        window_seconds=60,
    )
    result = await service.compute_deal_health(
        tenant_id=user["tenant_id"],
        opportunity_id=opportunity_id,
        user_id=user["user_id"],
    )
    return DealHealthResponse(
        opportunity_id=opportunity_id,
        health=HealthBand(result.health),
        confidence=result.confidence,
        risk_factors=result.risk_factors,
        recommended_actions=result.recommended_actions,
        engagement_velocity=result.engagement_velocity,
        days_in_stage=result.days_in_stage,
        computed_at=datetime.now(UTC),
    )


@router.post(
    "/opportunities/sweep",
    response_model=DealHealthSweepResponse,
)
async def sweep_deal_health(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[CrmAiService, Depends(get_crm_service)],
) -> DealHealthSweepResponse:
    """Recheck + persist deal health for every open opportunity closing within
    the next 12 months (the manual twin of the scheduled nightly sweep)."""
    await limiter.enforce(
        key=f"ai:crm:{user['tenant_id']}:{user['user_id']}",
        limit=settings.RATE_LIMIT_CRM_PER_MIN,
        window_seconds=60,
    )
    await limiter.enforce(
        key=f"ai:tenant_total:{user['tenant_id']}",
        limit=settings.RATE_LIMIT_TENANT_PER_MIN,
        window_seconds=60,
    )
    result = await service.sweep_deal_health(
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
    )
    return DealHealthSweepResponse(
        assessed=result.assessed,
        healthy=result.healthy,
        at_risk=result.at_risk,
        critical=result.critical,
    )


# ---------------------------------------------------------------------------
# Follow-up management
# ---------------------------------------------------------------------------


@router.get("/follow-ups", response_model=list[FollowUpItem])
async def list_follow_ups(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[CrmAiService, Depends(get_crm_service)],
) -> list[FollowUpItem]:
    """List pending follow-up suggestions for the authenticated user."""
    await limiter.enforce(
        key=f"ai:crm:{user['tenant_id']}:{user['user_id']}",
        limit=settings.RATE_LIMIT_CRM_PER_MIN,
        window_seconds=60,
    )
    rows = await service.list_pending_follow_ups(
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
    )
    return [_follow_up_to_item(row) for row in rows]


@router.post("/follow-ups/{suggestion_id}/apply", response_model=FollowUpItem)
async def apply_follow_up(
    suggestion_id: uuid.UUID,
    body: dict[str, Any],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[CrmAiService, Depends(get_crm_service)],
) -> FollowUpItem:
    """Apply a pending follow-up suggestion (one-click send).

    The request body must contain ``activity_id`` - the UUID of the CRM
    activity created in core by the caller.
    """
    await limiter.enforce(
        key=f"ai:crm_apply:{user['tenant_id']}:{user['user_id']}",
        limit=settings.RATE_LIMIT_CRM_APPLY_PER_MIN,
        window_seconds=60,
    )
    await limiter.enforce(
        key=f"ai:tenant_total:{user['tenant_id']}",
        limit=settings.RATE_LIMIT_TENANT_PER_MIN,
        window_seconds=60,
    )
    activity_id_raw = body.get("activity_id")
    if activity_id_raw is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="activity_id is required")
    activity_id = uuid.UUID(str(activity_id_raw))

    row = await service.apply_follow_up(
        tenant_id=user["tenant_id"],
        suggestion_id=suggestion_id,
        user_id=user["user_id"],
        activity_id=activity_id,
    )
    return _follow_up_to_item(row)


@router.post("/follow-ups/{suggestion_id}/dismiss", response_model=FollowUpItem)
async def dismiss_follow_up(
    suggestion_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[CrmAiService, Depends(get_crm_service)],
) -> FollowUpItem:
    """Dismiss a pending follow-up suggestion."""
    await limiter.enforce(
        key=f"ai:crm_apply:{user['tenant_id']}:{user['user_id']}",
        limit=settings.RATE_LIMIT_CRM_APPLY_PER_MIN,
        window_seconds=60,
    )
    await limiter.enforce(
        key=f"ai:tenant_total:{user['tenant_id']}",
        limit=settings.RATE_LIMIT_TENANT_PER_MIN,
        window_seconds=60,
    )
    row = await service.dismiss_follow_up(
        tenant_id=user["tenant_id"],
        suggestion_id=suggestion_id,
        user_id=user["user_id"],
    )
    return _follow_up_to_item(row)
