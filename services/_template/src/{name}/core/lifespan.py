"""Application lifespan — startup and graceful shutdown.

Extracted from main.py for testability and separation of concerns.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from {name}.core.config import Environment, settings
from {name}.core.logging import configure_{name}_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and graceful shutdown."""
    configure_{name}_logging(log_level=settings.LOG_LEVEL, json_output=settings.LOG_JSON)

    logger = get_logger("{name}.startup")
    logger.info(
        "service.starting",
        environment=settings.ENVIRONMENT.value,
        debug=settings.DEBUG,
        log_level=settings.LOG_LEVEL,
    )

    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    yield

    from {name}.db.session import engine

    await engine.dispose()
