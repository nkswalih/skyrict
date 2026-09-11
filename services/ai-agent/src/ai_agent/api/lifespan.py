"""Application lifespan - startup verification and graceful shutdown.

Extracted from main.py for testability and separation of concerns.

Startup: configures structured logging and verifies every required dependency
ONCE (database, Redis, JWT public key) and refuses to boot on failure - the
orchestrator sees the non-zero exit and restarts the pod instead of serving
traffic with a dead dependency. The readiness gate only opens after
verification succeeds; ``GET /ready`` reports it (with lightweight live
probes) but never re-runs this verification.

AI providers are intentionally absent from this gate - see api/readiness.py.

Shutdown: closes the gate so probes drain the pod, then disposes the DB
engine and the Redis pool.

Background jobs (SKY-68/SKY-90): suggestion expiry, anomaly auto-close, anomaly
scan, Audit Guardian weekly reports, and memory compaction run as asyncio tasks
started after provider init and cancelled on shutdown. The orchestrating jobs
live in api/scheduled (not core/jobs) because they compose feature services;
repository-only jobs stay in core/jobs.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_agent.api import readiness
from ai_agent.core.config import settings
from ai_agent.core.llm_router import LlmRouter
from ai_agent.core.logging import configure_logging, get_logger
from ai_agent.core.providers import build_providers_from_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan - startup and graceful shutdown."""
    configure_logging(log_level=settings.LOG_LEVEL, json_output=settings.LOG_JSON)

    logger = get_logger("ai_agent.startup")
    logger.info(
        "service.starting",
        environment=settings.ENVIRONMENT.value,
        debug=settings.DEBUG,
        log_level=settings.LOG_LEVEL,
        inventory_service_url=settings.INVENTORY_SERVICE_URL,
    )

    # Startup verification - fail-fast: any failure raises StartupError and
    # the process exits immediately (orchestrator restarts the pod).
    await readiness.verify_startup_dependencies()
    readiness.mark_ready()

    # Provider chain: built ONCE at startup; an unknown provider key raises
    # StartupError and refuses boot. Zero providers is a VALID configuration -
    # AI endpoints then degrade to typed 503s while health/readiness stay green.
    llm_router = LlmRouter(build_providers_from_settings(settings))
    app.state.llm_router = llm_router
    logger.info(
        "service.started",
        environment=settings.ENVIRONMENT.value,
        providers_configured=llm_router.provider_count,
    )

    # Cross-module narrator (SKY-63): optional daily cron + system agent row.
    # Disabled by default; only starts when explicitly enabled AND a provider is
    # configured (the digest requires the LLM).
    narrator_scheduler: object | None = None
    if settings.NARRATOR_SCHEDULER_ENABLED and llm_router.has_providers:
        from ai_agent.db.agent_registry_repository import AgentRegistryRepository
        from ai_agent.db.session import async_session_factory
        from ai_agent.features.narrator.scheduler import NarratorScheduler

        async def _enabled_tenants() -> list[tuple[uuid.UUID, str]]:
            # Placeholder tenant enumeration. Production wiring lists enabled
            # tenants from the platform directory; keeping it empty here means
            # the cron runs but generates nothing until a tenant provider lands.
            return []

        async def _service_factory(tenant_id: uuid.UUID, slug: str) -> object:
            from sqlalchemy.ext.asyncio import AsyncSession

            from ai_agent.core.audit_service import AuditService
            from ai_agent.db.audit_repository import AiAuditLogRepository
            from ai_agent.db.digest_repository import DigestCacheRepository
            from ai_agent.features.narrator.gateway import HttpCoreGateway
            from ai_agent.features.narrator.service import NarratorService

            session: AsyncSession = async_session_factory()
            return NarratorService(
                gateway=HttpCoreGateway(
                    base_url=str(settings.INVENTORY_SERVICE_URL),
                    bearer_token="",  # nosec B106 - system-agent wiring; token lands with tenant provider
                    tenant_slug=slug,
                ),
                llm_router=llm_router,
                cache=DigestCacheRepository(session),
                audit=AuditService(AiAuditLogRepository(session)),
                allow_llm=settings.NARRATOR_ALLOW_LLM,
                allow_refresh=True,
            )

        scheduler = NarratorScheduler(
            tenant_provider=_enabled_tenants,
            service_factory=_service_factory,  # type: ignore[arg-type]
            hour=settings.NARRATOR_DAILY_HOUR,
            minute=settings.NARRATOR_DAILY_MINUTE,
            timezone=settings.NARRATOR_SCHEDULER_TIMEZONE,
        )
        scheduler.start()
        narrator_scheduler = scheduler
        try:
            async with async_session_factory() as session:
                await AgentRegistryRepository(session).upsert_system_agent(
                    name="narrator", module="ai_agent.features.narrator"
                )
                await session.commit()
            logger.info("narrator.agent_registered")
        except Exception:
            logger.exception("narrator.agent_registration_failed")

    # Weekly L3 compliance digest (HR-AI-003): optional APScheduler cron over
    # all active tenants. Disabled by default; starts only when enabled AND a
    # service token is provisioned AND a provider is configured (the digest
    # requires the LLM to narrate).
    l3_weekly_scheduler: object | None = None
    if (
        settings.L3_WEEKLY_DIGEST_ENABLED
        and settings.L3_WEEKLY_DIGEST_SERVICE_TOKEN
        and llm_router.has_providers
    ):
        from ai_agent.api.scheduled.l3_weekly_digest import L3WeeklyDigestScheduler
        from ai_agent.db.session import async_session_factory

        async def _l3_enabled_tenants() -> list[tuple[uuid.UUID, str]]:
            from ai_agent.db.repository import TenantRepository

            async with async_session_factory() as session:
                tenants = await TenantRepository(session).list_active()
            return [(tenant.id, tenant.slug) for tenant in tenants]

        async def _l3_service_factory(tenant_id: uuid.UUID, slug: str) -> object:
            from sqlalchemy.ext.asyncio import AsyncSession

            from ai_agent.core.audit_service import AuditService
            from ai_agent.db.audit_repository import AiAuditLogRepository
            from ai_agent.db.l3_narrative_repository import L3NarrativeRepository
            from ai_agent.features.l3.gateway import HttpL3CoreGateway
            from ai_agent.features.l3.service import L3NarrativeService

            session: AsyncSession = async_session_factory()
            return L3NarrativeService(
                gateway=HttpL3CoreGateway(
                    base_url=str(settings.INVENTORY_SERVICE_URL),
                    bearer_token=settings.L3_WEEKLY_DIGEST_SERVICE_TOKEN,
                    tenant_slug=slug,
                ),
                llm_router=llm_router,
                cache=L3NarrativeRepository(session),
                audit=AuditService(AiAuditLogRepository(session)),
                allow_llm=settings.NARRATOR_ALLOW_LLM,
                allow_refresh=settings.L3_ALLOW_REFRESH,
            )

        l3_scheduler = L3WeeklyDigestScheduler(
            tenant_provider=_l3_enabled_tenants,
            service_factory=_l3_service_factory,  # type: ignore[arg-type]
            day_of_week=settings.L3_WEEKLY_DIGEST_DAY_OF_WEEK,
            hour=settings.L3_WEEKLY_DIGEST_HOUR,
            minute=settings.L3_WEEKLY_DIGEST_MINUTE,
            timezone=settings.NARRATOR_SCHEDULER_TIMEZONE,
        )
        l3_scheduler.start()
        l3_weekly_scheduler = l3_scheduler
        try:
            from ai_agent.db.agent_registry_repository import AgentRegistryRepository

            async with async_session_factory() as session:
                await AgentRegistryRepository(session).upsert_system_agent(
                    name="l3_weekly", module="ai_agent.features.l3"
                )
                await session.commit()
            logger.info("l3_weekly.agent_registered")
        except Exception:
            logger.exception("l3_weekly.agent_registration_failed")

    # Weekly revenue-forecast refresh (SKY-82 A4): optional cron calling the
    # core finance-forecast recompute. Disabled by default; tenant enumeration
    # is a placeholder like the narrator's, so the cron runs but refreshes
    # nothing until a tenant provider lands.
    forecast_scheduler: object | None = None
    if settings.FORECAST_SCHEDULER_ENABLED:
        from ai_agent.features.revenue_forecast.scheduler import RevenueForecastScheduler

        async def _forecast_tenants() -> list[tuple[uuid.UUID, str]]:
            return []

        async def _refresh_factory(tenant_id: uuid.UUID, slug: str) -> object:
            from ai_agent.features.revenue_forecast.client import CoreForecastRefreshClient

            return CoreForecastRefreshClient(
                base_url=str(settings.INVENTORY_SERVICE_URL),
                bearer_token="",  # nosec B106 - system-agent wiring; token lands with tenant provider
                tenant_slug=slug,
            )

        forecast_scheduler = RevenueForecastScheduler(
            tenant_provider=_forecast_tenants,
            refresh_factory=_refresh_factory,  # type: ignore[arg-type]
            day_of_week=settings.FORECAST_SCHEDULER_DAY_OF_WEEK,
            hour=settings.FORECAST_SCHEDULER_HOUR,
            minute=settings.FORECAST_SCHEDULER_MINUTE,
            timezone=settings.FORECAST_SCHEDULER_TIMEZONE,
        )
        forecast_scheduler.start()

    # --- Background jobs (SKY-68) -----------------------------------------
    bg_tasks: list[asyncio.Task[None]] = []
    from ai_agent.api.scheduled.anomaly_scan import run_scheduled_anomaly_scan
    from ai_agent.api.scheduled.crm_follow_up_scan import run_crm_follow_up_scan
    from ai_agent.api.scheduled.deal_health_sweep import run_deal_health_sweep
    from ai_agent.api.scheduled.guardian_report import run_scheduled_guardian_report
    from ai_agent.api.scheduled.memory_compaction import run_scheduled_memory_compaction
    from ai_agent.core.jobs.anomaly_autoclose import run_anomaly_autoclose_job
    from ai_agent.core.jobs.suggestion_expiry import run_suggestion_expiry_job

    bg_tasks.append(asyncio.create_task(run_suggestion_expiry_job()))
    bg_tasks.append(asyncio.create_task(run_anomaly_autoclose_job()))
    bg_tasks.append(asyncio.create_task(run_scheduled_anomaly_scan()))
    bg_tasks.append(asyncio.create_task(run_crm_follow_up_scan()))
    bg_tasks.append(asyncio.create_task(run_deal_health_sweep()))
    bg_tasks.append(asyncio.create_task(run_scheduled_guardian_report(llm_router=llm_router)))
    bg_tasks.append(asyncio.create_task(run_scheduled_memory_compaction(llm_router=llm_router)))
    logger.info("background_jobs.started", count=len(bg_tasks))

    # Graceful shutdown: uvicorn owns SIGTERM/SIGINT handling; on signal it
    # runs this context manager's exit, closing the readiness gate and the
    # DB/Redis pools so in-flight work can drain cleanly.
    yield

    if narrator_scheduler is not None:
        narrator_scheduler.stop()  # type: ignore[attr-defined]

    if l3_weekly_scheduler is not None:
        l3_weekly_scheduler.stop()  # type: ignore[attr-defined]

    if forecast_scheduler is not None:
        forecast_scheduler.stop()  # type: ignore[attr-defined]

    # Cancel background jobs before disposing resources.
    for task in bg_tasks:
        task.cancel()
    await asyncio.gather(*bg_tasks, return_exceptions=True)

    readiness.mark_stopping()
    logger.info("service.stopping", environment=settings.ENVIRONMENT.value)

    from ai_agent.core.redis import close_redis
    from ai_agent.db.session import engine

    await close_redis()
    await engine.dispose()
