"""Weekly compliance digest scheduler - APScheduler cron (HR-AI-003).

Runs the L3 compliance digest once per week per active tenant at a
configured weekday/hour/minute (UTC). Optional (disabled by default via
``AI_L3_WEEKLY_DIGEST_ENABLED``), defensive (one tenant failing never crashes
the cron), and logged per run.

Authentication mirrors the anomaly-scan precedent: a background task has no
user JWT, so the pass authenticates with a provisioned service token
(``AI_L3_WEEKLY_DIGEST_SERVICE_TOKEN``) + per-tenant X-Tenant-Slug. Empty
token disables the scheduled pass (log-only).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import TYPE_CHECKING

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from ai_agent.features.l3.service import L3NarrativeService

logger = structlog.get_logger("ai_agent.l3_weekly_digest")

TenantProvider = Callable[[], Awaitable[list[tuple[uuid.UUID, str]]]]
ServiceFactory = Callable[[uuid.UUID, str], Awaitable["L3NarrativeService"]]


class L3WeeklyDigestScheduler:
    """One async cron job producing each active tenant's weekly compliance digest."""

    def __init__(
        self,
        *,
        tenant_provider: TenantProvider,
        service_factory: ServiceFactory,
        day_of_week: str,
        hour: int,
        minute: int,
        timezone: str,
    ) -> None:
        self._tenant_provider = tenant_provider
        self._service_factory = service_factory
        self._day_of_week = day_of_week
        self._hour = hour
        self._minute = minute
        self._timezone = timezone
        self._scheduler: AsyncIOScheduler | None = None

    def start(self) -> None:
        if self._scheduler is not None:
            return
        scheduler = AsyncIOScheduler(timezone=self._timezone)
        scheduler.add_job(
            self._run_all,
            CronTrigger(
                day_of_week=self._day_of_week,
                hour=self._hour,
                minute=self._minute,
                timezone=self._timezone,
            ),
            id="l3_weekly_compliance_digest",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
        scheduler.start()
        self._scheduler = scheduler
        logger.info(
            "l3_weekly_digest.started",
            day_of_week=self._day_of_week,
            hour=self._hour,
            minute=self._minute,
        )

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("l3_weekly_digest.stopped")

    async def _run_all(self) -> None:
        tenants = await self._tenant_provider()
        for tenant_id, slug in tenants:
            try:
                service = await self._service_factory(tenant_id, slug)
                await service.generate(
                    kind="compliance_digest",
                    tenant_id=tenant_id,
                    user_id=None,
                    as_of=date.today(),
                    force_refresh=False,
                )
                await service.commit()
                logger.info(
                    "l3_weekly_digest.tenant_completed",
                    tenant_id=str(tenant_id),
                    tenant_slug=slug,
                )
            except Exception:
                logger.exception("l3_weekly_digest.tenant_failed", tenant_id=str(tenant_id))
