"""Suggestion expiry job - auto-expires pending restock suggestions (spec 3.4).

Runs periodically within the FastAPI lifespan. Any suggestion with
status='pending' and created_at older than SUGGESTION_EXPIRY_DAYS is
bulk-updated to status='expired'.
"""

from __future__ import annotations

import asyncio

import structlog

from ai_agent.core.config import settings

logger = structlog.get_logger("ai_agent.jobs.suggestion_expiry")

# How often to check for stale suggestions (in seconds).
_INTERVAL_SECONDS = 3600  # once per hour


async def run_suggestion_expiry_job() -> None:
    """Background loop that expires stale pending suggestions."""
    while True:
        try:
            from ai_agent.db.session import async_session_factory

            async with async_session_factory() as session:
                from ai_agent.db.suggestion_repository import SuggestionRepository

                repo = SuggestionRepository(session)
                expired_count = await repo.expire_stale(
                    expiry_days=settings.SUGGESTION_EXPIRY_DAYS,
                )
                await session.commit()
                if expired_count > 0:
                    logger.info(
                        "suggestion_expiry.completed",
                        expired=expired_count,
                        expiry_days=settings.SUGGESTION_EXPIRY_DAYS,
                    )
        except Exception:
            logger.exception("suggestion_expiry.failed")
        await asyncio.sleep(_INTERVAL_SECONDS)
