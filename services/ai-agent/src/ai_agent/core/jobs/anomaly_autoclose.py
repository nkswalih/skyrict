"""Anomaly auto-close job - dismisses open anomalies after 30 days (spec 4.4).

Runs periodically within the FastAPI lifespan. Any anomaly with
status='open' and created_at older than ANOMALY_AUTO_CLOSE_DAYS is
bulk-updated to status='dismissed' with a system note.
"""

from __future__ import annotations

import asyncio

import structlog

from ai_agent.core.config import settings

logger = structlog.get_logger("ai_agent.jobs.anomaly_autoclose")

# How often to check for stale anomalies (in seconds).
_INTERVAL_SECONDS = 3600  # once per hour


async def run_anomaly_autoclose_job() -> None:
    """Background loop that auto-closes stale open anomalies."""
    while True:
        try:
            from ai_agent.db.session import async_session_factory

            async with async_session_factory() as session:
                from ai_agent.db.anomaly_repository import AnomalyRepository

                repo = AnomalyRepository(session)
                closed_count = await repo.auto_close_stale(
                    close_days=settings.ANOMALY_AUTO_CLOSE_DAYS,
                )
                await session.commit()
                if closed_count > 0:
                    logger.info(
                        "anomaly_autoclose.completed",
                        closed=closed_count,
                        close_days=settings.ANOMALY_AUTO_CLOSE_DAYS,
                    )
        except Exception:
            logger.exception("anomaly_autoclose.failed")
        await asyncio.sleep(_INTERVAL_SECONDS)
