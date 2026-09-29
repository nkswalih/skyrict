"""Async database engine and session factory - the ONE place DB connections are created.

Sets Row-Level Security context on every transaction: when the request-scoped
TenantContext is populated, ``app.current_tenant_id`` is set via
``set_config(..., true)`` (transaction-local) so Postgres RLS policies
(``public.current_tenant_id()``) bound every query to the current tenant.

The middleware's pre-context tenant lookup (and any bootstrap/seed work that
runs without a request) does not set the GUC, so it stays unconstrained.

Event wiring follows the SQLAlchemy asyncio docs: events are attached to the
*sync* ``sessionmaker`` that backs the ``async_sessionmaker`` (via
``sync_session_class``); ``after_begin`` then fires on the sync ``Connection``
inside the greenlet bridge, before any statement of the transaction runs.

After-commit events (docs §2.5) are drained on the sync ``after_commit`` hook:
by then the COMMIT is durable, so an event is only observable after its write
survives - and the drain is scheduled as a background task on the running
loop, so a failing publish can never turn a successful request into a 500.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from core.core.config import settings
from core.core.logging import get_logger
from core.core.tenant_context import TenantContext
from core.events.producers import (
    buffered_events,
    clear_event_buffer,
    flush_events,
    start_event_buffer,
)

logger = get_logger("core.db.session")

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)

_sync_session_factory = sessionmaker(
    engine.sync_engine,
    class_=Session,
    expire_on_commit=False,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    sync_session_class=_sync_session_factory,
)


@event.listens_for(_sync_session_factory, "after_begin")
def _set_rls_tenant_context(_session: Session, _transaction: object, connection: object) -> None:
    """Set the RLS tenant on every new transaction when a tenant is in scope."""
    tenant_id = TenantContext.get_optional()
    if tenant_id is None:
        return
    connection.exec_driver_sql(  # type: ignore[attr-defined]
        "SELECT set_config('app.current_tenant_id', $1, true)",
        (tenant_id,),
    )


def _log_flush_failure(task: asyncio.Task[object]) -> None:
    """Log a failed after-commit flush without propagating into the request."""
    try:
        task.result()
    except Exception:
        logger.exception(
            "events.after_commit_flush_failed",
            message="after-commit event flush failed; request already succeeded",
        )


@event.listens_for(_sync_session_factory, "after_commit")
def _drain_event_buffer(_session: Session) -> None:
    """Publish buffered events as a background task once the COMMIT is durable.

    Runs on the loop that executed the commit (we're inside the greenlet
    bridge of an ``await session.commit()``); scheduling a task means the
    request does not wait on - and can never fail because of - the publish.
    If no loop is running (e.g. an out-of-request commit) there is nothing
    durable to coordinate with, so the buffer is dropped with a warning.
    """
    if not buffered_events():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "events.after_commit_no_loop",
            message="no running loop for after-commit flush; dropping buffered events",
        )
        clear_event_buffer()
        return
    task = loop.create_task(flush_events())
    task.add_done_callback(_log_flush_failure)


@event.listens_for(_sync_session_factory, "after_rollback")
def _discard_event_buffer(_session: Session) -> None:
    """Discard buffered events on rollback - nothing rolled back may be emitted."""
    clear_event_buffer()


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency - yields an async session; commit on success.

    Commits when the handler completes successfully, rolls back otherwise:
    without the commit every write made by a route handler would be rolled
    back when the session closes.

    Domain events emitted during the request are buffered (docs §2.5: events
    fire AFTER commit). The buffer is drained by the ``after_commit`` listener
    above and discarded by ``after_rollback`` - nothing here publishes events.
    """
    start_event_buffer()
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        finally:
            await session.close()


async def commit_writes(db: AsyncSession) -> None:
    """Make a route handler's writes durable BEFORE it returns its response.

    ``get_db`` commits in the dependency teardown, which for a ``yield``
    dependency runs at the very tail of the request - after the handler built
    its response. A client that trusts the 2xx and immediately re-reads the
    row is therefore racing the commit, and when it loses the read returns the
    PREVIOUS state. That is not a cosmetic race: a board that moves a deal and
    re-reads the pipeline can render the card back in its old column and settle
    there, looking like the move silently failed.

    Routes whose response a client will read back from should take
    ``db: AsyncSession = Depends(get_db)`` and call this as their last
    statement. The teardown's ``commit()`` then has nothing left to do, so
    this is purely about ordering, not about double-committing. The event
    buffer still drains on the real COMMIT, so after-commit publishes keep
    their "never before durable" guarantee.

    Read-only routes do not need it - they have nothing to make durable.
    """
    await db.commit()
