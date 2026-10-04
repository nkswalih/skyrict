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
anti-join for tenants that hold identity grants but no ``core_user_roles`` rows -
the table ``require_permission`` actually reads - and repairs those tenants only,
one transaction each, by calling the SAME ``sync_rbac_from_identity(tenant_id)``
the boot path uses. There is no second projection implementation to drift from.

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
owns both ``core_roles`` and ``core_user_roles``. That is checked ONCE at
startup, for both tables the tick reads: if the role ever loses the capability
the anti-join would silently match nothing and this worker would look healthy
while doing nothing, so it refuses to start and logs an error instead.

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
# throwaway postgres:16 with pgvector, 10,000 tenants / 40,000 roles / 50,000
# grants, EXPLAIN (ANALYZE, BUFFERS, TIMING OFF), mean of five runs after a
# warm-up. Three candidate gap queries, same fixture, same session:
#
#   scenario              gaps   A: core_roles     B: core_user_roles   C: grant-level
#   healthy                  0    44.67 ms              44.90 ms          845.96 ms
#   fresh signup gap       109    27.00 ms              31.75 ms         1104.20 ms
#   roles, grants gone    109    33.80 ms   MISSES      54.46 ms          841.31 ms
#   partial grants         109    42.87 ms   MISSES      44.51 ms  MISSES   814.04 ms
#   total outage         10000    45.90 ms              33.21 ms            6.89 ms
#
# A is the earlier revision of this query, which keyed the anti-join off
# `core_roles`; the MISSES column is gaps each candidate failed to find. B is
# chosen: same cost as A, but it finds the roles-projected-grants-missing
# tenant that A silently reported as healthy. C is the exact inverse of step
# 3's DELETE and finds everything, at 15-35x the cost - 1104 ms worst case is
# 22% duty at the active interval, 44% across two replicas, on a 0.25-CPU box.
#
# Worst case for B is 54.46 ms. Beta runs minReplicas=1 / maxReplicas=2, so two
# ticks cost at most ~109 ms of database time per period: 1.1% duty against the
# active interval, 0.09% against the idle cap.
#
# The idle cap, not the active interval, is what sets how long a new tenant
# waits. Sign-ups are rare, so the loop is almost always at the cap, and a
# tenant created just after a tick waits one whole period - which makes the
# cap the worst case, not the 5 s active interval. Measured on a booted
# service against this schema: 4.9 s while the loop was already active, 13.4 s
# and 70.2 s mid-ramp, 323.6 s with the cap at 300 s, and 55.5 s at the 60 s
# cap this ships.
#
# The cap is 60 s because five minutes of a locked-out tenant owner is a poor
# trade against 0.09% duty. The incident this fixes ran ~29 minutes.
_ACTIVE_INTERVAL_SECONDS = 5.0
_IDLE_INTERVAL_CAP_SECONDS = 60.0

# Without a cap, a total outage reconciles 10,000 tenants as 10,000
# transactions inside one tick, on a 0.25-CPU container. Capping bounds every
# tick; at the active interval the backlog still drains in a few minutes.
_MAX_TENANTS_PER_TICK = 200

# A reconcile that projects no grants is a data-integrity anomaly, not backlog.
# ``user_roles`` has no composite FK to ``roles(tenant_id, id)``, so a grant
# whose denormalised tenant_id disagrees with its role's tenant can never match
# step 2's pinned role-name join. Such a tenant stays selected by the gap query
# forever - correctly, since it is still locked out - so this cooldown is what
# stops the tick re-attempting it every few seconds and flooding the log.
#
# Cooldown, never a permanent blacklist: if the underlying row is repaired the
# tenant reconciles again on the first pass after this window.
#
# This counts ``core_user_roles`` rather than ``core_roles`` so the signal means
# "no access was projected" instead of "no roles were projected". Counting
# ``core_roles`` could not distinguish a healthy repair from the anomaly, because
# step 1 populates it either way.
_NO_PROGRESS_COOLDOWN_SECONDS = 900.0

# +/-20% of the period.
_JITTER_FRACTION = 0.2

# Driven from `tenants` so the cost tracks tenant count rather than total
# grant count, and gated on an existing grant so a tenant that legitimately
# has no grants yet is never selected.
#
# The anti-join tests `core_user_roles`, NOT `core_roles`. That distinction is
# the whole correctness of this query, and an earlier revision got it wrong by
# keying off `core_roles`:
#
#   A tenant holding identity grants but no core_roles rows  (never projected)
#   A tenant holding identity grants and core_roles rows but no
#     core_user_roles rows                                    (roles landed,
#                                                               grants did not)
#
# Step 1 writes `core_roles` and step 2 writes `core_user_roles`, both in one
# transaction. A tenant in the second state is the one that matters: step 1
# succeeds, step 2's role-name join matches nothing, and the tenant ends up
# with a role catalog and zero access. Keyed off `core_roles` the tick saw that
# tenant as healthy, logged it as reconciled, and then never selected it again
# because the presence of core_roles satisfied the anti-join. `core_user_roles`
# is the table `require_permission` actually reads, so it is the table whose
# absence means lockout, and it is what this query tests.
#
# Not tested here: a tenant with SOME grants projected and others missing. That
# needs a per-grant anti-join, which measured 15-35x the cost of this form in
# every scenario where grants are projected - and cheaper only in a total
# outage, where `core_user_roles` is empty and the anti-join short-circuits.
# See the measurement block above. It is reachable only if identity holds a
# grant whose role belongs to a different tenant - a defect that is already a
# privilege-escalation bug in identity, because identity's own reconcile treats
# any tenant_owner holder as full access regardless of tenant. Such a tenant
# keeps partial access rather than none.
_GAP_TENANTS_SQL = text(
    "SELECT t.id "
    "FROM tenants t "
    "WHERE EXISTS (SELECT 1 FROM user_roles ur WHERE ur.tenant_id = t.id) "
    "AND NOT EXISTS (SELECT 1 FROM core_user_roles cur WHERE cur.tenant_id = t.id) "
    "ORDER BY t.id "
    "LIMIT :limit"
)

# Checked for BOTH tables the tick reads. Ownership alone is per-table, so a
# role owning only `core_roles` would pass a single-table check and then have
# RLS silently filter its reads of `core_user_roles` - which would make every
# tenant look unprojected and every tick select every tenant.
_CAN_BYPASS_RLS_SQL = text(
    "SELECT r.rolsuper "
    "    OR r.rolbypassrls "
    "    OR (SELECT count(*) = 2 "
    "        FROM pg_class c "
    "        WHERE c.oid IN ('core_roles'::regclass, 'core_user_roles'::regclass) "
    "          AND c.relowner = r.oid) "
    "FROM pg_roles r "
    "WHERE r.rolname = current_user"
)

_COUNT_CORE_USER_ROLES_SQL = text(
    "SELECT count(*) FROM core_user_roles WHERE tenant_id = :tenant_id"
)


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
                        "core_roles and core_user_roles, so the tenant anti-join "
                        "would silently match nothing; reconciler not started"
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

    async def _count_core_user_roles(self, tenant_id: uuid.UUID) -> int:
        async with self._session_factory() as session:
            value = await session.scalar(_COUNT_CORE_USER_ROLES_SQL, {"tenant_id": tenant_id})
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
            # whole or not at all. Counting core_user_roles is what makes this
            # meaningful: counting core_roles could not tell a healthy repair
            # from a failed one, because step 1 populates it either way.
            if await self._count_core_user_roles(tenant_id) == 0:
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
                            "projected no core_user_roles rows; cooling down"
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
