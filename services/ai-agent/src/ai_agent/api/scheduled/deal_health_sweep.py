"""Scheduled deal-health sweep - daily background job (SKY-61).

Every day, for every active tenant, rechecks deal health for every open
opportunity expected to close within the forecasting horizon (the deals the
finance forecast card shows). Runs the SAME deterministic engine as the manual
per-deal and bulk endpoints and writes the SAME ``ai_deal_health`` rows, so the
card's health dots stay fresh with no one having to trigger a check.

Lives under ``ai_agent.api.scheduled`` (not ``core/jobs``) because it
orchestrates feature services and depends on the CRM gateway - the same
architectural boundary that places the follow-up scan here.

Authentication: the sweep runs as a system task with no user JWT. It
authenticates with the CRM service token (``CRM_SCAN_SERVICE_TOKEN``) and
forwards a per-tenant ``X-Tenant-Slug``. Empty token disables the pass
(log-only), mirroring the follow-up scan. Audits attribute to the deal owner
when one exists (the scheduled pass has no acting user).

Isolation: tenant enumeration uses the ``tenants_readable`` policy (no GUC),
then each tenant opens its own session and sets ``TenantContext`` before the
first CRM query. One tenant's failure never aborts others.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.audit_events import AI_DEAL_HEALTH_ASSESSED
from ai_agent.core.audit_service import AuditService
from ai_agent.core.config import settings
from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.audit_repository import AiAuditLogRepository
from ai_agent.db.repository import TenantRepository
from ai_agent.db.session import async_session_factory
from ai_agent.features.crm.deal_health import OpportunitySignals, assess_deal_health
from ai_agent.features.crm.gateway import HttpCrmGateway
from ai_agent.features.crm.repositories import CrmAiRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger("ai_agent.scheduled.deal_health_sweep")

# One daily pass keeps the dots fresh without hammering core's CRM API.
_INTERVAL_SECONDS = 86400

# Deals expected to close within this window are the ones the forecast card
# counts; checking anything else would be wasted work.
_HORIZON_DAYS = 365


async def _sweep_tenant(
    *,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    base_url: str,
    service_token: str,
    session_factory: Callable[[], AsyncSession],
) -> None:
    """Recheck every horizon deal's health for one tenant under its RLS context."""
    async with session_factory() as session:
        TenantContext.set(str(tenant_id))
        TenantContext.set_tenant_slug(tenant_slug)

        gateway = HttpCrmGateway(
            base_url=base_url,
            bearer_token=service_token,
            tenant_slug=tenant_slug,
        )
        repo = CrmAiRepository(session)
        audit = AuditService(AiAuditLogRepository(session))

        now = datetime.now(UTC)
        today = now.date()
        horizon_end = (now + timedelta(days=_HORIZON_DAYS)).date()

        assessed = 0
        for opp in await gateway.list_opportunities():
            if opp.expected_close_date is None:
                continue
            if not today <= opp.expected_close_date <= horizon_end:
                continue
            activities = await gateway.list_activities_for_entity(
                entity_type="opportunity", entity_id=opp.id
            )
            result = assess_deal_health(
                signals=OpportunitySignals(
                    opportunity_id=opp.id,
                    stage=opp.stage,
                    probability=opp.probability,
                    has_amount=opp.has_amount,
                    created_at=opp.created_at,
                    last_stage_change_at=opp.last_stage_change_at,
                    expected_close_date=opp.expected_close_date,
                ),
                activities=activities,
                now=now,
            )
            await repo.save_deal_health_assessment(
                tenant_id=tenant_id,
                opportunity_id=opp.id,
                health=result.health,
                confidence=result.confidence,
                risk_factors=result.risk_factors,
                recommended_actions=result.recommended_actions,
            )
            if opp.owner_id is not None:
                await audit.log(
                    action=AI_DEAL_HEALTH_ASSESSED,
                    tenant_id=tenant_id,
                    user_id=opp.owner_id,
                    input_payload={"opportunity_id": str(opp.id)},
                    output_payload={
                        "health": result.health,
                        "confidence": result.confidence,
                    },
                )
            assessed += 1

        await session.commit()
        logger.info(
            "deal_health_sweep.tenant_completed",
            tenant_id=str(tenant_id),
            assessed=assessed,
        )


async def scan_all_tenants(
    *,
    service_token: str,
    base_url: str,
    session_factory: Callable[[], AsyncSession] = async_session_factory,
    sweep_factory: Callable[..., Awaitable[None]] = _sweep_tenant,
) -> None:
    """Run one sweep per active tenant; failures isolated per tenant."""
    if not service_token:
        logger.debug("deal_health_sweep.skipped_no_service_token")
        return
    async with session_factory() as listing_session:
        tenants = await TenantRepository(listing_session).list_active()
    if not tenants:
        logger.debug("deal_health_sweep.no_active_tenants")
        return
    for tenant in tenants:
        try:
            await sweep_factory(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                base_url=base_url,
                service_token=service_token,
                session_factory=session_factory,
            )
        except Exception:
            logger.exception("deal_health_sweep.tenant_failed", tenant_id=str(tenant.id))


async def run_deal_health_sweep() -> None:
    """Background loop: one deal-health sweep per day."""
    while True:
        try:
            await scan_all_tenants(
                service_token=settings.CRM_SCAN_SERVICE_TOKEN,
                base_url=settings.INVENTORY_SERVICE_URL,
            )
        except Exception:
            logger.exception("deal_health_sweep.pass_failed")
        await asyncio.sleep(_INTERVAL_SECONDS)
