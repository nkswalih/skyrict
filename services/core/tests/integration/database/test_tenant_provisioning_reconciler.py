"""Regression: tenants created after migration 0039 have no default packs.

Every per-tenant default pack - leave types, payroll settings, the chart of
accounts, the Phase-1 report definitions and the approval definitions - was
reachable only from the manual ``core seed --tenant-id`` command. Nothing ran
them at provisioning time. Identity's self-service signup writes the tenant and
the owner's role grants but never calls core, and ``identity.tenant.provisioned``
is published to a logging-only stub with no consumer (see
``core/events/consumers/__init__.py``).

Consequence, observed on a production tenant: a tenant created after core
migration 0039 had zero rows in ``erp_report_definitions``, so
``ReportService.get_report`` raised ``Report '<slug>' was not found`` for every
one of the twelve Phase-1 reports. ``seed_reporting_defaults`` and its siblings
were covered by tests that call them DIRECTLY, which is why the suite stayed
green while no production path invoked them.

``provision_tenant_defaults`` and ``TenantProvisioningReconciler`` close that
window. These tests exercise the entry point and the reconciler against a bare
tenant and assert the reports become listable through the service that the API
actually calls.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select, text

from core.db.session import async_session_factory
from core.features.provisioning.worker import (
    ProvisionOutcome,
    TenantProvisioningReconciler,
)
from core.features.reporting.repository import ReportRepository
from core.features.reporting.seeds import PHASE_1_REPORT_SEEDS
from core.features.reporting.service import ReportService
from core.models.core_role import CoreRoleModel
from core.models.core_user_role import CoreUserRoleModel
from core.models.tenant import TenantModel
from core.seed import provision_tenant_defaults

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

pytestmark = pytest.mark.integration

_EXPECTED_REPORT_SLUGS = frozenset(seed.slug for seed in PHASE_1_REPORT_SEEDS)

# One count per pack. Static statement objects, never string-built SQL, so the
# test does not need a Bandit suppression for the table name.
_PACK_COUNT_SQL = {
    "leave_types": text("SELECT count(*) FROM erp_leave_types WHERE tenant_id = :tenant_id"),
    "payroll_settings": text(
        "SELECT count(*) FROM erp_payroll_settings WHERE tenant_id = :tenant_id"
    ),
    "chart_of_accounts": text(
        "SELECT count(*) FROM erp_chart_of_accounts WHERE tenant_id = :tenant_id"
    ),
    "report_definitions": text(
        "SELECT count(*) FROM erp_report_definitions WHERE tenant_id = :tenant_id"
    ),
    "approval_definitions": text(
        "SELECT count(*) FROM erp_approval_workflow_definitions WHERE tenant_id = :tenant_id"
    ),
}

_ALL_PACKS = tuple(_PACK_COUNT_SQL)


@dataclass(frozen=True)
class BareTenant:
    """A tenant as signup leaves it: the row exists, no core packs do."""

    tenant_id: uuid.UUID


async def _create_bare_tenant(prefix: str) -> BareTenant:
    tenant_id = uuid.uuid4()
    async with async_session_factory() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name=f"{prefix.title()} Tenant",
                slug=f"{prefix}-{tenant_id.hex[:8]}",
                plan_tier="free",
                is_active=True,
            )
        )
        await session.commit()
    return BareTenant(tenant_id=tenant_id)


async def _delete_tenant(tenant_id: uuid.UUID) -> None:
    """Remove a tenant; the composite-PK FKs cascade to every child table."""
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id})
        await session.commit()


async def _pack_counts(tenant_id: uuid.UUID) -> dict[str, int]:
    async with async_session_factory() as session:
        return {
            pack: (await session.execute(sql, {"tenant_id": tenant_id})).scalar_one()
            for pack, sql in _PACK_COUNT_SQL.items()
        }


async def _core_rbac_counts(tenant_id: uuid.UUID) -> tuple[int, int]:
    async with async_session_factory() as session:
        roles = (
            await session.execute(
                select(func.count())
                .select_from(CoreRoleModel)
                .where(CoreRoleModel.tenant_id == tenant_id)
            )
        ).scalar_one()
        grants = (
            await session.execute(
                select(func.count())
                .select_from(CoreUserRoleModel)
                .where(CoreUserRoleModel.tenant_id == tenant_id)
            )
        ).scalar_one()
    return roles, grants


async def _list_report_slugs(tenant_id: uuid.UUID) -> set[str]:
    """The slugs ``GET /api/v1/reports`` would return for this tenant."""
    async with async_session_factory() as session:
        definitions = await ReportService(ReportRepository(session)).list_reports(
            tenant_id=tenant_id
        )
    return {definition.slug for definition in definitions}


@pytest.fixture
async def bare_tenant(migrated_schema: None) -> AsyncGenerator[BareTenant, None]:
    created = await _create_bare_tenant("provision")
    try:
        yield created
    finally:
        await _delete_tenant(created.tenant_id)


class TestProvisionTenantDefaults:
    async def test_bare_tenant_has_no_packs(self, bare_tenant: BareTenant) -> None:
        """Precondition: the state that caused the production 404s."""
        counts = await _pack_counts(bare_tenant.tenant_id)
        assert counts == dict.fromkeys(_ALL_PACKS, 0)
        assert await _list_report_slugs(bare_tenant.tenant_id) == set()

    async def test_applies_every_pack(self, bare_tenant: BareTenant) -> None:
        await provision_tenant_defaults(bare_tenant.tenant_id)

        counts = await _pack_counts(bare_tenant.tenant_id)
        assert all(counts[pack] > 0 for pack in _ALL_PACKS), counts
        assert counts["report_definitions"] == len(PHASE_1_REPORT_SEEDS)

    async def test_reports_are_listable_through_the_service(self, bare_tenant: BareTenant) -> None:
        """The proving test: the reported 404 path starts returning definitions.

        ``ReportService.get_report`` is exactly what raises
        ``Report '<slug>' was not found``; it is exercised here through the same
        service the reports router calls, not through the repository directly.
        """
        await provision_tenant_defaults(bare_tenant.tenant_id)

        assert await _list_report_slugs(bare_tenant.tenant_id) == _EXPECTED_REPORT_SLUGS

        async with async_session_factory() as session:
            service = ReportService(ReportRepository(session))
            definition = await service.get_report(
                tenant_id=bare_tenant.tenant_id, slug="pnl_by_period"
            )
        assert definition.slug == "pnl_by_period"

    async def test_is_idempotent(self, bare_tenant: BareTenant) -> None:
        await provision_tenant_defaults(bare_tenant.tenant_id)
        first = await _pack_counts(bare_tenant.tenant_id)

        await provision_tenant_defaults(bare_tenant.tenant_id)

        assert await _pack_counts(bare_tenant.tenant_id) == first

    async def test_does_not_write_core_rbac(self, bare_tenant: BareTenant) -> None:
        """Provisioning must never create core's RBAC mirror.

        ``core_roles``/``core_user_roles`` stay a projection of identity's
        grants (SKY-120). ``seed_core_roles_for_tenant`` is deliberately not
        part of the pack because it unions core's static permission lists into
        existing rows, which can widen access beyond what identity granted.
        """
        assert await _core_rbac_counts(bare_tenant.tenant_id) == (0, 0)

        await provision_tenant_defaults(bare_tenant.tenant_id)

        assert await _core_rbac_counts(bare_tenant.tenant_id) == (0, 0)


class TestTenantProvisioningReconciler:
    async def test_run_once_provisions_a_gap_tenant(self, bare_tenant: BareTenant) -> None:
        reconciler = TenantProvisioningReconciler(async_session_factory, max_tenants_per_tick=1000)

        outcome = await reconciler.run_once()

        assert isinstance(outcome, ProvisionOutcome)
        assert outcome.gap_tenants >= 1
        counts = await _pack_counts(bare_tenant.tenant_id)
        assert all(counts[pack] > 0 for pack in _ALL_PACKS), counts

    async def test_completed_tenant_is_not_reselected(self, bare_tenant: BareTenant) -> None:
        reconciler = TenantProvisioningReconciler(async_session_factory, max_tenants_per_tick=1000)
        await reconciler.run_once()
        provisioned = await _pack_counts(bare_tenant.tenant_id)

        await reconciler.run_once()

        assert await _pack_counts(bare_tenant.tenant_id) == provisioned

    async def test_partial_gap_is_repaired(self, bare_tenant: BareTenant) -> None:
        """A tenant missing only one pack is still a gap and is repaired."""
        await provision_tenant_defaults(bare_tenant.tenant_id)
        async with async_session_factory() as session:
            await session.execute(
                text("DELETE FROM erp_report_definitions WHERE tenant_id = :tid"),
                {"tid": bare_tenant.tenant_id},
            )
            await session.commit()
        assert await _list_report_slugs(bare_tenant.tenant_id) == set()

        await TenantProvisioningReconciler(
            async_session_factory, max_tenants_per_tick=1000
        ).run_once()

        assert await _list_report_slugs(bare_tenant.tenant_id) == _EXPECTED_REPORT_SLUGS

    async def test_failure_is_isolated_and_cooled_down(
        self,
        bare_tenant: BareTenant,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from core.features.provisioning import worker as worker_module

        real_provision = worker_module.provision_tenant_defaults

        async def _fail_for_this_tenant(tenant_id: uuid.UUID) -> None:
            if tenant_id == bare_tenant.tenant_id:
                raise RuntimeError("simulated seed failure")
            await real_provision(tenant_id)

        monkeypatch.setattr(worker_module, "provision_tenant_defaults", _fail_for_this_tenant)
        reconciler = TenantProvisioningReconciler(async_session_factory, max_tenants_per_tick=1000)

        first = await reconciler.run_once()
        assert first.tenants_failed >= 1
        assert (await _pack_counts(bare_tenant.tenant_id))["report_definitions"] == 0

        # The next pass must not retry a tenant that just failed.
        second = await reconciler.run_once()
        assert second.tenants_cooling_down >= 1
        assert (await _pack_counts(bare_tenant.tenant_id))["report_definitions"] == 0

    async def test_cooling_tenants_do_not_starve_a_due_tenant(
        self, bare_tenant: BareTenant
    ) -> None:
        """A failing tenant must not hold a tick slot forever.

        The gap query is capped, so with a bare LIMIT the same failing tenants
        (ordered by id) would be returned on every pass and the tenants behind
        them would never be reached. The fetch limit is widened by the number
        of cooling tenants so at least max_tenants_per_tick due candidates are
        always visible.
        """
        other = await _create_bare_tenant("cooling")
        due_tenant = await _create_bare_tenant("due")
        try:
            reconciler = TenantProvisioningReconciler(async_session_factory, max_tenants_per_tick=1)
            loop_time = asyncio.get_running_loop().time()
            # Cool down every gap except the one this pass must reach, so the
            # assertion does not depend on UUID ordering or on other rows in
            # the shared test database.
            gaps = await reconciler._gap_tenant_ids(1000)
            reconciler._retry_at = {
                tid: loop_time + 300.0 for tid in gaps if tid != due_tenant.tenant_id
            }

            await reconciler.run_once()

            assert (await _pack_counts(due_tenant.tenant_id))["report_definitions"] > 0
            assert (await _pack_counts(bare_tenant.tenant_id))["report_definitions"] == 0
        finally:
            await _delete_tenant(other.tenant_id)
            await _delete_tenant(due_tenant.tenant_id)

    async def test_refuses_to_start_without_rls_bypass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A role that cannot bypass RLS would make the anti-join match nothing."""

        async def _cannot_write(self: TenantProvisioningReconciler) -> bool:
            return False

        monkeypatch.setattr(TenantProvisioningReconciler, "_can_write", _cannot_write)
        reconciler = TenantProvisioningReconciler(async_session_factory)

        reconciler.start()
        try:
            for _ in range(100):
                await asyncio.sleep(0)
                if not reconciler.running:
                    break
            assert not reconciler.running
        finally:
            await reconciler.stop()

    async def test_loop_provisions_then_stops(self, bare_tenant: BareTenant) -> None:
        reconciler = TenantProvisioningReconciler(async_session_factory, max_tenants_per_tick=1000)

        reconciler.start()
        try:
            for _ in range(400):
                counts = await _pack_counts(bare_tenant.tenant_id)
                if all(counts[pack] > 0 for pack in _ALL_PACKS):
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("reconciler did not provision the gap tenant within 20s")
        finally:
            await reconciler.stop()

        assert not reconciler.running
        assert await _list_report_slugs(bare_tenant.tenant_id) == _EXPECTED_REPORT_SLUGS
