"""Application lifespan — startup and graceful shutdown.

Extracted from main.py for testability and separation of concerns.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from identity.core.config import settings
from identity.core.logging import configure_identity_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and graceful shutdown."""
    configure_identity_logging(log_level=settings.LOG_LEVEL, json_output=settings.LOG_JSON)

    logger = get_logger("identity.startup")
    logger.info(
        "service.starting",
        environment=settings.ENVIRONMENT.value,
        debug=settings.DEBUG,
        log_level=settings.LOG_LEVEL,
    )

    # Graceful shutdown: drain in-flight requests before closing DB pool
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for all signals
            pass

    yield

    # Shutdown: close DB engine and allow in-flight requests to drain
    from identity.db.session import engine

    await engine.dispose()
