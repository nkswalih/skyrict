"""In-process RBAC projection reconciler (SKY-120).

Self-service signup provisions a tenant by writing its role catalog and the
owner's grant straight into the shared database (``roles`` + ``user_roles``)
and emitting ``identity.tenant.provisioned``. Nothing consumes that event:
identity's ``publish_event`` is a logging-only stub and core's RBAC consumer
states in its own docstring that no broker loop is wired. Core's RBAC tables
were therefore written in exactly one place - ``sync_rbac_from_identity()`` at
BOOT - so a tenant created between two restarts had identity grants but no
core projection, and its owner got 403 on every ``require_permission`` check.

This worker closes that window out of band. Each tick runs one indexed
anti-join for tenants that hold identity grants but no ``core_roles`` rows, and
repairs those tenants only, one transaction each, by calling the SAME
``sync_rbac_from_identity(tenant_id)`` the boot path uses. There is no second
projection implementation to drift from.

Three properties make this safe to run unattended:

- **No request-path writes.** Nothing here touches an authorization read. A
  check either sees the projection or it does not; it never triggers one.
- **Additive only.** The scoped call skips ``sync_rbac_from_identity``'s
  revocation DELETE, so a tick can restore missing access but never remove
  any. No user's access is widened beyond what identity grants, because the
  rows copied are exactly identity's rows.
- **Bounded and idempotent.** Every statement is ``ON CONFLICT``-guarded, so
  concurrent replicas converge rather than conflict, and a per-tick cap keeps
  any single tick short.

RLS: core's RBAC tables are protected by ``tenant_id =
current_tenant_id()``, and a background task has no request tenant, so
``app.current_tenant_id`` is unset and the GUC reads NULL. The tick therefore
relies on the database role bypassing RLS - core's role carries BYPASSRLS and
owns ``core_roles``. That is checked ONCE at startup: if the role ever loses
the capability the anti-join would silently match nothing and this worker
would look healthy while doing nothing, so it refuses to start and logs an
error instead.

Owned by the core app lifespan (``api/lifespan.py``), guarded by
``RBAC_PROJECTION_ENABLED`` and disabled under the test environment so
integration tests drive ``run_once()`` directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
import socket
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

from core.seed import sync_rbac_from_identity

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Intervals and caps below are derived from measurements, not guesses. On a
# throwaway postgres:16 with pgvector, 10,000 tenants / 50,000 grants / 40,000
# roles, EXPLAIN (ANALYZE, BUFFERS), mean of five runs after a warm-up:
#
#   healthy, 0 gaps      25.6 ms   Nested Loop Semi Join over Hash Anti Join;
#                                    the user_roles Index Only Scan is
#                                    "never executed", so the steady-state
#                                    tick never reads the grants table
#   partial, 1108 gaps   18.5 ms
#   total outage         41.7 ms
#
# An earlier `user_roles`-driven anti-join measured 36.1 ms healthy, and a
# variant that also tested for missing core_user_roles measured 205 ms, so
# both were rejected. Beta runs minReplicas=1 / maxReplicas=2, so two ticks
# cost at most ~83 ms of database time per period: 1.7% duty against the
# active interval, 0.07% against the idle cap at the 41.7 ms worst case.
#
# The idle cap, not the active interval, is what sets how long a new tenant
# waits. Sign-ups are rare, so the loop is almost always at the cap, and a
# tenant created just after a tick waits one whole period - which makes the
# cap the worst case, not the 5 s active interval. Measured on a booted
# service against this schema: 4.9 s while the loop was already active, 13.4 s
# and 70.2 s mid-ramp, and 323.6 s with the cap at 300 s.
#
# The cap is 60 s because five minutes of a locked-out tenant owner is a poor
# trade against 0.07% duty. The incident this fixes ran ~29 minutes, so even
# the measured 300 s cap was a 5.4x improvement - but an owner meeting 403s
# throughout is the exact failure being fixed, and the extra polling is noise.
_ACTIVE_INTERVAL_SECONDS = 5.0
_IDLE_INTERVAL_CAP_SECONDS = 60.0

# Without a cap, a total outage reconciles 10,000 tenants as 10,000
# transactions inside one tick, on a 0.25-CPU container. Capping bounds every
# tick; at the active interval the backlog still drains in a few minutes.
_MAX_TENANTS_PER_TICK = 200

# A reconcile that creates nothing is a data-integrity anomaly, not backlog.
# ``user_roles`` has no composite FK to ``roles(tenant_id, id)``, so a grant
# whose denormalised tenant_id disagrees with its role's tenant can never
# match, and the tick would otherwise re-select it forever. Cooldown, never a
# permanent blacklist - if the underlying row is repaired, the tenant
# reconciles again on the next pass after this window.
_NO_PROGRESS_COOLDOWN_SECONDS = 900.0

# +/-20% of the period.
_JITTER_FRACTION = 0.2

# Driven from `tenants` so the cost tracks tenant count rather than total
# grant count, and gated on an existing grant so a tenant that legitimately
# has no grants yet is never selected.
_GAP_TENANTS_SQL = text(
    "SELECT t.id "
    "FROM tenants t "
    "WHERE EXISTS (SELECT 1 FROM user_roles ur WHERE ur.tenant_id = t.id) "
    "AND NOT EXISTS (SELECT 1 FROM core_roles cr WHERE cr.tenant_id = t.id) "
    "ORDER BY t.id "
    "LIMIT :limit"
)

_CAN_BYPASS_RLS_SQL = text(
    "SELECT r.rolsuper OR r.rolbypassrls OR c.relowner = r.oid "
    "FROM pg_roles r "
    "JOIN pg_class c ON c.oid = 'core_roles'::regclass "
    "WHERE r.rolname = current_user"
)

_COUNT_CORE_ROLES_SQL = text("SELECT count(*) FROM core_roles WHERE tenant_id = :tenant_id")


@dataclass(frozen=True)
class ReconcileOutcome:
    """Result of one reconcile pass, for the log line and the tests."""

    gap_tenants: int
    tenants_reconciled: int
    tenants_failed: int
    tenants_no_progress: int
    tenants_cooling_down: int


class RbacProjectionReconciler:
    """Background loop that projects identity's grants into core's RBAC tables."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_tenants_per_tick: int = _MAX_TENANTS_PER_TICK,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._max_tenants_per_tick = max_tenants_per_tick
        self._clock = clock
        # tenant_id -> monotonic time at which its cooldown expires.
        self._cooldowns: dict[uuid.UUID, float] = {}
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._worker_id = f"core-{socket.gethostname()}-{os.getpid()}"

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Begin the background reconcile loop (idempotent)."""
        if self.running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="rbac-projection-reconciler")

    async def stop(self, *, timeout: float = 5.0) -> None:
        """Signal the loop to stop and await it (cancels on timeout)."""
        self._stop.set()
        task, self._task = self._task, None
        if task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run_loop(self) -> None:
        if not await self._can_bypass_rls():
            logger.error(
                "rbac.projection.rls_not_bypassable",
                extra={
                    "worker_id": self._worker_id,
                    # Not "message": reserved LogRecord attribute.
                    "detail": (
                        "database role cannot bypass Row-Level Security on "
                        "core_roles, so the tenant anti-join would silently "
                        "match nothing; reconciler not started"
                    ),
                },
            )
            return
        logger.info(
            "rbac.projection.started",
            extra={
                "worker_id": self._worker_id,
                "max_tenants_per_tick": self._max_tenants_per_tick,
            },
        )
        interval = _ACTIVE_INTERVAL_SECONDS
        try:
            while not self._stop.is_set():
                reconciled = 0
                try:
                    outcome = await self.run_once()
                    reconciled = outcome.tenants_reconciled
                    if reconciled or outcome.tenants_no_progress:
                        logger.info(
                            "rbac.projection.pass",
                            extra={"worker_id": self._worker_id, **vars(outcome)},
                        )
                except Exception:
                    logger.exception(
                        "rbac.projection.pass_failed", extra={"worker_id": self._worker_id}
                    )
                interval = (
                    _ACTIVE_INTERVAL_SECONDS
                    if reconciled
                    else min(interval * 2, _IDLE_INTERVAL_CAP_SECONDS)
                )
                await self._sleep(self._jitter(interval))
        finally:
            logger.info("rbac.projection.stopped", extra={"worker_id": self._worker_id})

    async def _sleep(self, seconds: float) -> None:
        """Sleep, but wake immediately when stop() is called.

        The suppressed TimeoutError is the wait expiring, which is the normal
        path - it is not an error being discarded.
        """
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)

    def _jitter(self, seconds: float) -> float:
        """Spread the wait so replicas do not tick on the same boundary."""
        spread = seconds * _JITTER_FRACTION
        return seconds + random.uniform(-spread, spread)

    async def _can_bypass_rls(self) -> bool:
        """True when the database role can see across tenants.

        Without this the anti-join would match nothing under a tenant policy
        and the worker would report healthy forever while repairing nothing.
        """
        async with self._session_factory() as session:
            value = await session.scalar(_CAN_BYPASS_RLS_SQL)
        return bool(value)

    async def _gap_tenant_ids(self) -> list[uuid.UUID]:
        async with self._session_factory() as session:
            rows = await session.execute(_GAP_TENANTS_SQL, {"limit": self._max_tenants_per_tick})
        return [row[0] for row in rows]

    async def _count_core_roles(self, tenant_id: uuid.UUID) -> int:
        async with self._session_factory() as session:
            value = await session.scalar(_COUNT_CORE_ROLES_SQL, {"tenant_id": tenant_id})
        return int(value or 0)

    async def run_once(self) -> ReconcileOutcome:
        """Reconcile one batch of gap tenants. Safe to call directly."""
        gap_tenants = await self._gap_tenant_ids()
        now = self._clock()
        due = [tid for tid in gap_tenants if self._cooldowns.get(tid, 0.0) <= now]
        cooling = len(gap_tenants) - len(due)

        reconciled = 0
        failed = 0
        no_progress = 0
        for tenant_id in due:
            try:
                # One transaction per tenant: a failure here can never roll
                # back another tenant's projection.
                await sync_rbac_from_identity(tenant_id)
            except Exception:
                # One tenant's failure never aborts the pass, and never
                # escapes into the loop.
                failed += 1
                logger.exception(
                    "rbac.projection.tenant_failed",
                    extra={"worker_id": self._worker_id, "tenant_id": str(tenant_id)},
                )
                continue
            reconciled += 1
            # Both INSERTs share one transaction, so the tenant is projected
            # whole or not at all - zero rows afterwards means nothing landed.
            if await self._count_core_roles(tenant_id) == 0:
                no_progress += 1
                self._cooldowns[tenant_id] = now + _NO_PROGRESS_COOLDOWN_SECONDS
                logger.warning(
                    "rbac.projection.tenant_no_progress",
                    extra={
                        "worker_id": self._worker_id,
                        "tenant_id": str(tenant_id),
                        "cooldown_seconds": _NO_PROGRESS_COOLDOWN_SECONDS,
                        # Not "message": that is a reserved LogRecord attribute
                        # and extra= would raise KeyError.
                        "detail": (
                            "identity holds grants for this tenant but they "
                            "projected no core_roles rows; cooling down"
                        ),
                    },
                )
            else:
                self._cooldowns.pop(tenant_id, None)

        return ReconcileOutcome(
            gap_tenants=len(gap_tenants),
            tenants_reconciled=reconciled,
            tenants_failed=failed,
            tenants_no_progress=no_progress,
            tenants_cooling_down=cooling,
        )


__all__ = ["RbacProjectionReconciler", "ReconcileOutcome"]
