"""Scheduled Audit Guardian weekly report - per-tenant background job (SKY-90).

Every week, for every active tenant, generates the integrity report for the
previous 7-day window using the SAME ``GuardianReportService`` the API routers
use, so operators get a report without anyone having to trigger one.

Lives under ``ai_agent.api.scheduled`` (not ``core/jobs``) because it
orchestrates feature services - the same architectural boundary that places
the anomaly scan here.

Readers: production wiring registers only the in-service ``ai_agent`` reader
(:class:`AiAuditLogReader`); the ``core``/``identity`` audit trails live in
other services' databases with no read projection or HTTP gateway here, so
those sources log the service's designed ``reader_missing`` warning and the
report proceeds on the events this service can read.

Isolation: tenant enumeration runs against the permissive ``tenants_readable``
policy (no GUC set), then each tenant's pass opens its OWN session and sets
``TenantContext`` before the first query - the transaction-local ``set_config``
(db/session.py) then scopes every RLS-guarded row. One tenant's failure never
aborts the pass for the others.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.audit_service import AuditService
from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.ai_audit_log_reader import AiAuditLogReader
from ai_agent.db.audit_repository import AiAuditLogRepository
from ai_agent.db.guardian_report_repository import GuardianReportRepository
from ai_agent.db.repository import TenantRepository
from ai_agent.db.session import async_session_factory
from ai_agent.features.audit_guardian.service import GuardianReportService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ai_agent.core.llm_router import LlmRouter

logger = structlog.get_logger("ai_agent.scheduled.guardian_report")

# Weekly cadence keeps the report aligned with the service's 7-day window.
_INTERVAL_SECONDS = 7 * 24 * 60 * 60


async def _generate_tenant_report(
    *,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    session_factory: Callable[[], AsyncSession],
    llm_router: LlmRouter | None = None,
) -> None:
    """Generate one tenant's weekly report under its RLS context."""
    async with session_factory() as session:
        TenantContext.set(str(tenant_id))
        TenantContext.set_tenant_slug(tenant_slug)

        service = GuardianReportService(
            report_repo=GuardianReportRepository(session),
            readers={"ai_agent": AiAuditLogReader(session)},
            audit=AuditService(AiAuditLogRepository(session)),
            llm_router=llm_router,
        )
        summary = await service.generate_weekly_report(tenant_id=tenant_id)
        await session.commit()
        logger.info(
            "guardian_report.tenant_completed",
            tenant_id=str(tenant_id),
            report_id=summary["report_id"],
            week_start=summary["week_start"],
            week_end=summary["week_end"],
            total_events_scanned=summary["total_events_scanned"],
            flagged_count=summary["flagged_count"],
        )


async def generate_reports_for_all_tenants(
    *,
    session_factory: Callable[[], AsyncSession] = async_session_factory,
    report_factory: Callable[..., Awaitable[None]] = _generate_tenant_report,
    llm_router: LlmRouter | None = None,
) -> None:
    """Run one weekly report per active tenant; failures isolated per tenant."""
    async with session_factory() as listing_session:
        tenants = await TenantRepository(listing_session).list_active()
    if not tenants:
        logger.debug("guardian_report.no_active_tenants")
        return
    for tenant in tenants:
        try:
            await report_factory(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                session_factory=session_factory,
                llm_router=llm_router,
            )
        except Exception:
            logger.exception(
                "guardian_report.tenant_failed",
                tenant_id=str(tenant.id),
                tenant_slug=tenant.slug,
            )


async def run_scheduled_guardian_report(llm_router: LlmRouter | None = None) -> None:
    """Background loop: one weekly report generation pass per tenant."""
    while True:
        try:
            await generate_reports_for_all_tenants(llm_router=llm_router)
        except Exception:
            logger.exception("guardian_report.pass_failed")
        await asyncio.sleep(_INTERVAL_SECONDS)
