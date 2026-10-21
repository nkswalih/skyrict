"""In-process tenant-defaults reconciler.

Self-service signup creates a tenant in the shared database, but core's
per-tenant reference packs - report definitions, HR defaults, the chart of
accounts and the approval-workflow definitions - were written in exactly one
place: the manual ``core seed --tenant-id`` command. Nothing ran them at
provisioning time, so a tenant created after core migration 0039 had no
report definitions at all and every ``/api/v1/reports/{slug}/run`` call for it
returned 404 ``Report '<slug>' was not found``.

The documented contract was never implemented. ``features/reporting/seeds.py``
states that "``core.seed`` applies the same pack when a new tenant is
provisioned"; ``events/consumers/__init__.py`` states that no broker loop is
wired, so ``identity.tenant.provisioned`` is published to a logging stub and
identity never calls core. Because both services share one database, core can
see a new tenant directly and repair the gap out of band - no broker needed.

Each tick runs one anti-join for active tenants missing *any* pack and
applies the same idempotent seed functions the CLI uses. There is no second
provisioning implementation to drift from.

Three properties make this safe to run unattended:

- **No request-path writes.** Nothing here touches an authorization read or a
  request handler; a request either sees the defaults or does not.
- **Additive by construction.** Every step reconciles what is missing and
  leaves matching rows untouched. It cannot delete, and it cannot widen
  access: RBAC is deliberately excluded (see ``provision_tenant_defaults``).
- **Bounded and idempotent.** A per-tick cap keeps any single tick short, and
  a completed tenant is never selected again.

RLS: the provisioned tables are protected by ``tenant_id =
current_tenant_id()`` and a background task has no request tenant, so
``app.current_tenant_id`` is unset. The tick therefore relies on the database
role bypassing RLS - either ``BYPASSRLS``/superuser, or ownership of all five
tables (no migration sets ``FORCE ROW LEVEL SECURITY``). That capability is
checked ONCE at startup: without it the anti-join would treat every tenant as a
gap and every write would fail its ``WITH CHECK``, so the worker refuses to
start and logs an error instead of looping on failures.

Owned by the core app lifespan (``api/lifespan.py``), guarded by
``TENANT_PROVISIONING_ENABLED`` and disabled under the test environment so
integration tests drive ``run_once()`` directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
import socket
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

from core.seed import provision_tenant_defaults

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# One anti-join per pack. A tenant is selected when ANY pack is absent, which
# is the provisioning gap: a tenant created after migration 0039 has none of
# them. Each step writes its whole pack in a single transaction, so a partial
# pack is not reachable through a crash - only genuine absence is tested.
_MISSING_DEFAULTS_SQL = text(
    "SELECT t.id "
    "FROM tenants t "
    "WHERE t.is_active IS TRUE "
    "AND ( "
    "    NOT EXISTS (SELECT 1 FROM erp_leave_types lt WHERE lt.tenant_id = t.id) "
    " OR NOT EXISTS (SELECT 1 FROM erp_payroll_settings ps WHERE ps.tenant_id = t.id) "
    " OR NOT EXISTS (SELECT 1 FROM erp_chart_of_accounts ca WHERE ca.tenant_id = t.id) "
    " OR NOT EXISTS (SELECT 1 FROM erp_report_definitions rd WHERE rd.tenant_id = t.id) "
    " OR NOT EXISTS ( "
    "        SELECT 1 FROM erp_approval_workflow_definitions awd "
    "        WHERE awd.tenant_id = t.id "
    "    ) "
    ") "
    "ORDER BY t.id "
    "LIMIT :limit"
)

# Writing to RLS-protected tables without a request tenant requires a role that
# bypasses RLS. Mirrors the RBAC reconciler's probe: superuser/BYPASSRLS, or
# ownership of every table the packs touch (a table owner bypasses RLS unless
# FORCE ROW LEVEL SECURITY is set - no migration sets it). Ownership alone is
# per-table, so all five must be owned: owning four would pass a partial check
# and then have RLS silently filter the fifth, which is exactly the silent
# no-op this probe exists to prevent. Asserted in ADR-0012.
_CAN_WRITE_SQL = text(
    "SELECT r.rolsuper "
    "    OR r.rolbypassrls "
    "    OR (SELECT count(*) = 5 "
    "        FROM pg_class c "
    "        WHERE c.oid IN ("
    "            'erp_leave_types'::regclass,"
    "            'erp_payroll_settings'::regclass,"
    "            'erp_chart_of_accounts'::regclass,"
    "            'erp_report_definitions'::regclass,"
    "            'erp_approval_workflow_definitions'::regclass"
    "        ) "
    "          AND c.relowner = r.oid "
    "          AND NOT c.relforcerowsecurity) "
    "FROM pg_roles r "
    "WHERE r.rolname = current_user"
)

# A new tenant must be usable within seconds, so the active interval matches
# the RBAC reconciler. The cap bounds the steady-state poll; the anti-join does
# no work when nothing is missing. Plan and timings are in ADR-0012.
_ACTIVE_INTERVAL_SECONDS = 5.0
_IDLE_INTERVAL_CAP_SECONDS = 60.0

# +/-20% of the period, so replicas do not tick on the same boundary.
_JITTER_FRACTION = 0.2

# Seeding a tenant costs four transactions plus the join, so keep a tick short.
_MAX_TENANTS_PER_TICK = 50

# A tenant that keeps failing is retried, but not on every tick.
_FAILURE_COOLDOWN_SECONDS = 300.0


@dataclass(frozen=True)
class ProvisionOutcome:
    """Result of one provisioning pass, for the log line and the tests."""

    gap_tenants: int
    tenants_provisioned: int
    tenants_failed: int
    tenants_cooling_down: int


class TenantProvisioningReconciler:
    """Background loop that applies missing per-tenant default packs."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_tenants_per_tick: int = _MAX_TENANTS_PER_TICK,
    ) -> None:
        self._session_factory = session_factory
        self._max_tenants_per_tick = max_tenants_per_tick
        self._worker_id = f"core-{socket.gethostname()}-{os.getpid()}"
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._retry_at: dict[uuid.UUID, float] = {}

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the loop. The first pass runs immediately."""
        if self.running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="tenant-provisioning")

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
        if not await self._can_write():
            logger.error(
                "provisioning.rls_not_bypassable",
                extra={
                    "worker_id": self._worker_id,
                    # Not "message": reserved LogRecord attribute.
                    "detail": (
                        "database role cannot bypass Row-Level Security on the "
                        "tenant-default tables, so every tenant would look "
                        "unprovisioned and every write would fail its RLS "
                        "check; reconciler not started"
                    ),
                },
            )
            return
        logger.info(
            "provisioning.started",
            extra={
                "worker_id": self._worker_id,
                "max_tenants_per_tick": self._max_tenants_per_tick,
            },
        )
        interval = _ACTIVE_INTERVAL_SECONDS
        try:
            while not self._stop.is_set():
                provisioned = 0
                try:
                    outcome = await self.run_once()
                    provisioned = outcome.tenants_provisioned
                    if provisioned or outcome.tenants_failed:
                        logger.info(
                            "provisioning.pass",
                            extra={"worker_id": self._worker_id, **vars(outcome)},
                        )
                except Exception:
                    logger.exception(
                        "provisioning.pass_failed", extra={"worker_id": self._worker_id}
                    )
                interval = (
                    _ACTIVE_INTERVAL_SECONDS
                    if provisioned
                    else min(interval * 2, _IDLE_INTERVAL_CAP_SECONDS)
                )
                await self._sleep(self._jitter(interval))
        finally:
            logger.info("provisioning.stopped", extra={"worker_id": self._worker_id})

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

    async def _can_write(self) -> bool:
        """True when the database role can write across tenants."""
        async with self._session_factory() as session:
            value = await session.scalar(_CAN_WRITE_SQL)
        return bool(value)

    async def _gap_tenant_ids(self, limit: int) -> list[uuid.UUID]:
        async with self._session_factory() as session:
            rows = await session.execute(_MISSING_DEFAULTS_SQL, {"limit": limit})
        return [row[0] for row in rows]

    async def run_once(self) -> ProvisionOutcome:
        """Provision one batch of gap tenants. Safe to call directly."""
        # Fetch past the cooling tenants: with a bare LIMIT, a tenant that keeps
        # failing could occupy a slot on every tick and starve the tenants behind
        # it. At most len(_retry_at) fetched tenants can be cooling, so this
        # limit always yields at least max_tenants_per_tick due candidates.
        gap_tenants = await self._gap_tenant_ids(self._max_tenants_per_tick + len(self._retry_at))
        loop_time = asyncio.get_running_loop().time()
        due = [tid for tid in gap_tenants if self._retry_at.get(tid, 0.0) <= loop_time]
        cooling = len(gap_tenants) - len(due)
        due = due[: self._max_tenants_per_tick]

        provisioned = 0
        failed = 0
        for tenant_id in due:
            try:
                await provision_tenant_defaults(tenant_id)
            except Exception:
                failed += 1
                self._retry_at[tenant_id] = loop_time + _FAILURE_COOLDOWN_SECONDS
                logger.exception(
                    "provisioning.tenant_failed",
                    extra={"worker_id": self._worker_id, "tenant_id": str(tenant_id)},
                )
                continue
            self._retry_at.pop(tenant_id, None)
            provisioned += 1

        return ProvisionOutcome(
            gap_tenants=len(gap_tenants),
            tenants_provisioned=provisioned,
            tenants_failed=failed,
            tenants_cooling_down=cooling,
        )


__all__ = ["ProvisionOutcome", "TenantProvisioningReconciler"]
