"""Weekly revenue-forecast scheduler - APScheduler cron (SKY-82 A4).

Clones the NarratorScheduler contract (SKY-63): one weekly async job that
refreshes each enabled tenant's forecast via the core finance-forecast API.
Disabled by default (``AI_FORECAST_SCHEDULER_ENABLED``), defensive - a single
tenant failing never crashes the cron - and every run is logged.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = structlog.get_logger("ai_agent.forecast_scheduler")

TenantProvider = Callable[[], Awaitable[list[tuple[uuid.UUID, str]]]]
RefreshFactory = Callable[[uuid.UUID, str], Awaitable[Callable[[], Awaitable[None]]]]


class RevenueForecastScheduler:
    """One weekly async cron refreshing every enabled tenant's forecast."""

    def __init__(
        self,
        *,
        tenant_provider: TenantProvider,
        refresh_factory: RefreshFactory,
        day_of_week: str,
        hour: int,
        minute: int,
        timezone: str,
    ) -> None:
        self._tenant_provider = tenant_provider
        self._refresh_factory = refresh_factory
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
            id="revenue_forecast_weekly",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
        scheduler.start()
        self._scheduler = scheduler
        logger.info(
            "forecast_scheduler.started",
            day_of_week=self._day_of_week,
            hour=self._hour,
            minute=self._minute,
        )

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("forecast_scheduler.stopped")

    async def _run_all(self) -> None:
        tenants = await self._tenant_provider()
        for tenant_id, slug in tenants:
            try:
                refresh = await self._refresh_factory(tenant_id, slug)
                await refresh()
            except Exception:
                logger.exception("forecast_scheduler.tenant_failed", tenant_id=tenant_id)
