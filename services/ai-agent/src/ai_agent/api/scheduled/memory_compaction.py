"""Scheduled episodic-to-semantic memory compaction - background job (SKY-90).

Every week, for every active tenant, folds older episodic rows into semantic
facts using the SAME ``MemoryCompactionService`` the memory feature exposes.
The service is repository-injected and needs no gateway, but it still lives
under ``ai_agent.api.scheduled`` (not ``core/jobs``) because it orchestrates
feature services - the same boundary that places the anomaly scan here.

Work set: per tenant, the job enumerates DISTINCT users that actually hold
uncompacted rows older than the compaction age (``COMPACTION_AGE_DAYS``) via
the memory repository - episodic rows are the source of truth for who has a
pending fold, not the platform user directory.

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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.memory_repository import MemoryRepository
from ai_agent.db.repository import TenantRepository
from ai_agent.db.session import async_session_factory
from ai_agent.features.memory_compaction.service import (
    COMPACTION_AGE_DAYS,
    MemoryCompactionService,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ai_agent.core.llm_router import LlmRouter

logger = structlog.get_logger("ai_agent.scheduled.memory_compaction")

# Weekly cadence keeps the fold window wide (see COMPACTION_AGE_DAYS).
_INTERVAL_SECONDS = 7 * 24 * 60 * 60


async def _compact_tenant(
    *,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    session_factory: Callable[[], AsyncSession],
    llm_router: LlmRouter | None = None,
) -> None:
    """Fold every pending user's older episodic rows under the tenant's RLS."""
    async with session_factory() as session:
        TenantContext.set(str(tenant_id))
        TenantContext.set_tenant_slug(tenant_slug)

        repo = MemoryRepository(session)
        service = MemoryCompactionService(repo=repo, llm_router=llm_router)

        before = datetime.now(UTC) - timedelta(days=COMPACTION_AGE_DAYS)
        user_ids = await repo.list_users_with_uncompacted_episodic(
            tenant_id=tenant_id, before=before
        )

        rows_processed = 0
        facts_stored = 0
        for user_id in user_ids:
            summary = await service.compact_user(tenant_id=tenant_id, user_id=user_id)
            rows_processed += summary.rows_processed
            facts_stored += summary.facts_stored

        await session.commit()
        logger.info(
            "memory_compaction.tenant_completed",
            tenant_id=str(tenant_id),
            users=len(user_ids),
            rows_processed=rows_processed,
            facts_stored=facts_stored,
        )


async def compact_all_tenants(
    *,
    session_factory: Callable[[], AsyncSession] = async_session_factory,
    compact_factory: Callable[..., Awaitable[None]] = _compact_tenant,
    llm_router: LlmRouter | None = None,
) -> None:
    """Run one compaction pass per active tenant; failures isolated per tenant."""
    async with session_factory() as listing_session:
        tenants = await TenantRepository(listing_session).list_active()
    if not tenants:
        logger.debug("memory_compaction.no_active_tenants")
        return
    for tenant in tenants:
        try:
            await compact_factory(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                session_factory=session_factory,
                llm_router=llm_router,
            )
        except Exception:
            logger.exception(
                "memory_compaction.tenant_failed",
                tenant_id=str(tenant.id),
                tenant_slug=tenant.slug,
            )


async def run_scheduled_memory_compaction(llm_router: LlmRouter | None = None) -> None:
    """Background loop: one compaction pass per week."""
    while True:
        try:
            await compact_all_tenants(llm_router=llm_router)
        except Exception:
            logger.exception("memory_compaction.pass_failed")
        await asyncio.sleep(_INTERVAL_SECONDS)
