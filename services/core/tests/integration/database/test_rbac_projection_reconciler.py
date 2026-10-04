"""SKY-120 regression: core RBAC projection for self-service signup tenants.

Identity's self-service signup writes the new tenant's role catalog and the
owner's grant straight into the SHARED database (``roles`` + ``user_roles``)
and emits ``identity.tenant.provisioned``. Nothing consumes that event:
``identity.events.producers.publish_event`` is a logging-only stub and core's
RBAC consumer states in its own docstring that no broker loop is wired. Core's
RBAC tables (``core_roles`` + ``core_user_roles``) were therefore written in
exactly one place - ``sync_rbac_from_identity()`` at BOOT.

Consequence: a tenant created by signup between two core restarts had identity
grants but no core projection of them, so ``RbacRepository`` resolved an empty
permission set for its owner and every ``require_permission`` check returned
403. Observed on beta: the owner of a tenant created at 07:50:49 UTC was locked
out for ~29 minutes until core happened to restart at 08:19:33.

``RbacProjectionReconciler`` closes that window. It projects identity's grants
into core's RBAC tables from a background task, so no request path ever writes
and authorization stays deterministic.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError

from core.db.rbac import RbacRepository, grants_permission
from core.db.session import async_session_factory
from core.models.core_role import CoreRoleModel
from core.models.core_user_role import CoreUserRoleModel
from core.models.tenant import TenantModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

pytestmark = pytest.mark.integration

# The roles identity's signup creates, mirroring SYSTEM_ROLE_DEFINITIONS
# (services/identity/src/identity/core/constants.py). Copied as literals on
# purpose: core and identity share a DATABASE, not a Python package, and the
# reconciler's contract is "mirror whatever identity has written", not "know
# identity's constants". Permission arrays are truncated to representative keys
# so the assertions stay readable; ``tenant_owner`` is reproduced exactly
# because it carries the invariant under test.
_SIGNUP_ROLE_DEFINITIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tenant_owner", ("*", "invitations:send")),
    ("organization_admin", ("users:read", "erp.inventory.read")),
    ("department_manager", ("users:read", "erp.inventory.read")),
    ("standard_user", ("users:read", "erp.inventory.read")),
    ("auditor", ("audit:read", "erp.inventory.read")),
    ("employee_self_service", ("erp.leave.self",)),
)


@dataclass(frozen=True)
class SignupTenant:
    """A tenant provisioned the way self-service signup provisions one."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID


async def _provision_signup_tenant(prefix: str) -> SignupTenant:
    """Write exactly what identity's signup writes, for one tenant.

    This is the exact post-signup state that caused the incident: identity has
    committed the role catalog and the owner's grant, and nothing has yet
    projected them into core.
    """
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

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

    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, password_hash, full_name) "
                "VALUES (:uid, :tid, :email, :hash, :name)"
            ),
            {
                "uid": user_id,
                "tid": tenant_id,
                "email": f"owner-{tenant_id.hex[:8]}@signup.skyrict.test",
                "hash": "not-a-real-hash",
                "name": "Signup Owner",
            },
        )
        role_ids: dict[str, uuid.UUID] = {}
        for name, permissions in _SIGNUP_ROLE_DEFINITIONS:
            role_id = uuid.uuid4()
            role_ids[name] = role_id
            await session.execute(
                text(
                    "INSERT INTO roles (id, tenant_id, name, permissions, is_system_role) "
                    "VALUES (:rid, :tid, :rname, :perms, true)"
                ),
                {"rid": role_id, "tid": tenant_id, "rname": name, "perms": list(permissions)},
            )
        # signup_create_organization grants the owner role to the owner.
        await session.execute(
            text(
                "INSERT INTO user_roles (id, tenant_id, user_id, role_id, scope_type, scope_id) "
                "VALUES (gen_random_uuid(), :tid, :uid, :rid, 'tenant', :tid)"
            ),
            {"tid": tenant_id, "uid": user_id, "rid": role_ids["tenant_owner"]},
        )
        await session.commit()

    return SignupTenant(tenant_id=tenant_id, user_id=user_id)


async def _delete_tenant(tenant_id: uuid.UUID) -> None:
    """Remove a tenant; the composite-PK FKs cascade to every child table."""
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id})
        await session.commit()


@pytest.fixture
async def signup_tenant(migrated_schema: None) -> AsyncGenerator[SignupTenant, None]:
    provisioned = await _provision_signup_tenant("signup")
    try:
        yield provisioned
    finally:
        await _delete_tenant(provisioned.tenant_id)


@pytest.fixture
async def captured_statements() -> AsyncGenerator[list[str], None]:
    """Every SQL statement the engine executes while the test runs."""
    from core.db.session import engine

    statements: list[str] = []

    def _record(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)


async def _core_rows(tenant_id: uuid.UUID) -> tuple[int, int]:
    """(core_roles, core_user_roles) row counts for one tenant."""
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


class TestSignupTenantProjection:
    async def test_owner_permissions_resolve_after_reconcile(
        self, signup_tenant: SignupTenant
    ) -> None:
        """The signup owner must stop getting 403 once a reconcile pass runs.

        Committed RED before the reconciler existed: this is the incident.
        """
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        tenant_id = signup_tenant.tenant_id

        # Precondition - the reported bug. Identity holds the grant; core holds
        # no projection of it, so the owner's permission set resolves empty.
        roles, grants = await _core_rows(tenant_id)
        assert (roles, grants) == (0, 0)
        async with async_session_factory() as session:
            assert (
                await RbacRepository(session).resolve_user_permissions(
                    user_id=signup_tenant.user_id, tenant_id=tenant_id
                )
                == []
            )

        outcome = await RbacProjectionReconciler(async_session_factory).run_once()

        assert outcome.tenants_reconciled == 1
        roles, grants = await _core_rows(tenant_id)
        assert roles == len(_SIGNUP_ROLE_DEFINITIONS)
        assert grants == 1

        async with async_session_factory() as session:
            permissions = await RbacRepository(session).resolve_user_permissions(
                user_id=signup_tenant.user_id, tenant_id=tenant_id
            )
        assert sorted(permissions) == ["*", "invitations:send"]
        assert grants_permission(permissions, "erp.inventory.read")


async def _role_permissions(tenant_id: uuid.UUID) -> dict[str, list[str]]:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(CoreRoleModel.name, CoreRoleModel.permissions).where(
                    CoreRoleModel.tenant_id == tenant_id
                )
            )
        ).all()
    return {name: sorted(permissions) for name, permissions in rows}


async def _grant_triples(tenant_id: uuid.UUID) -> list[tuple[str, str, str]]:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(
                    CoreUserRoleModel.user_id,
                    CoreUserRoleModel.role_id,
                    CoreUserRoleModel.scope_id,
                ).where(CoreUserRoleModel.tenant_id == tenant_id)
            )
        ).all()
    return sorted(
        (str(user_id), str(role_id), str(scope_id)) for user_id, role_id, scope_id in rows
    )


async def _drop_core_projection(tenant_id: uuid.UUID) -> None:
    """Reset core to the post-signup state; cascading FKs clear the grants."""
    async with async_session_factory() as session:
        await session.execute(
            text("DELETE FROM core_roles WHERE tenant_id = :tid"), {"tid": tenant_id}
        )
        await session.commit()


class TestSyncRbacFromIdentityTenantScope:
    """``tenant_id`` splits an additive projection from boot-time revocation."""

    async def test_scoped_run_projects_the_same_rows_as_the_boot_path(
        self, signup_tenant: SignupTenant
    ) -> None:
        """One implementation, two callers: both forms must agree exactly."""
        from core.seed import sync_rbac_from_identity

        tenant_id = signup_tenant.tenant_id

        await sync_rbac_from_identity(tenant_id)
        scoped_roles = await _role_permissions(tenant_id)
        scoped_grants = await _grant_triples(tenant_id)

        await _drop_core_projection(tenant_id)
        await sync_rbac_from_identity()
        unscoped_roles = await _role_permissions(tenant_id)
        unscoped_grants = await _grant_triples(tenant_id)

        assert scoped_roles == unscoped_roles
        assert scoped_grants == unscoped_grants
        assert len(scoped_roles) == len(_SIGNUP_ROLE_DEFINITIONS)

    async def test_scoped_run_issues_no_delete(
        self, signup_tenant: SignupTenant, captured_statements: list[str]
    ) -> None:
        """A background caller must never hold the power to revoke access."""
        from core.seed import sync_rbac_from_identity

        await sync_rbac_from_identity(signup_tenant.tenant_id)

        assert captured_statements, "expected the scoped sync to execute SQL"
        deletes = [s for s in captured_statements if s.lstrip().upper().startswith("DELETE")]
        assert deletes == []

    async def test_boot_path_still_deletes(
        self, signup_tenant: SignupTenant, captured_statements: list[str]
    ) -> None:
        """Companion to the assertion above - proves that check can fail.

        Without this, "no DELETE" would also hold if the sync had simply lost
        its revocation step everywhere.
        """
        from core.seed import sync_rbac_from_identity

        await sync_rbac_from_identity()

        deletes = [s for s in captured_statements if s.lstrip().upper().startswith("DELETE")]
        assert deletes, "the boot path must keep reconciling revoked grants"


async def _add_user_without_roles(tenant_id: uuid.UUID) -> uuid.UUID:
    """A user identity knows about but has granted nothing."""
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, password_hash, full_name) "
                "VALUES (:uid, :tid, :email, :hash, :name)"
            ),
            {
                "uid": user_id,
                "tid": tenant_id,
                "email": f"ungranted-{user_id.hex[:8]}@signup.skyrict.test",
                "hash": "not-a-real-hash",
                "name": "Ungranted User",
            },
        )
        await session.commit()
    return user_id


class TestReconcileScopeAndSafety:
    """The safety properties a reviewer will demand before merging this."""

    async def test_reconcile_never_touches_another_tenant(
        self, signup_tenant: SignupTenant
    ) -> None:
        """Repairing tenant A must leave tenant B completely untouched.

        ``run_once`` reconciles every gap it finds, so the assertion that
        matters is on the scoped call itself: given tenant A alone, tenant B
        must gain no rows and must stay denied.
        """
        from core.seed import sync_rbac_from_identity

        neighbour = await _provision_signup_tenant("neighbour")
        try:
            await sync_rbac_from_identity(signup_tenant.tenant_id)

            assert await _core_rows(signup_tenant.tenant_id) != (0, 0)
            assert await _core_rows(neighbour.tenant_id) == (0, 0)
            async with async_session_factory() as session:
                assert (
                    await RbacRepository(session).resolve_user_permissions(
                        user_id=neighbour.user_id, tenant_id=neighbour.tenant_id
                    )
                    == []
                )
        finally:
            await _delete_tenant(neighbour.tenant_id)

    async def test_reconcile_never_widens_beyond_identity_grants(
        self, signup_tenant: SignupTenant
    ) -> None:
        """Core's answer must equal identity's grants, key for key.

        The ungranted user is the load-bearing half: a projection that copied
        the whole role catalog onto every user, or that resolved permissions
        from the tenant rather than the user's grants, would pass an
        owner-only assertion and fail this one.
        """
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        ungranted = await _add_user_without_roles(signup_tenant.tenant_id)
        await RbacProjectionReconciler(async_session_factory).run_once()

        async with async_session_factory() as session:
            repository = RbacRepository(session)
            owner = await repository.resolve_user_permissions(
                user_id=signup_tenant.user_id, tenant_id=signup_tenant.tenant_id
            )
            other = await repository.resolve_user_permissions(
                user_id=ungranted, tenant_id=signup_tenant.tenant_id
            )

        assert sorted(owner) == ["*", "invitations:send"]
        assert other == []

    async def test_reconcile_is_idempotent(self, signup_tenant: SignupTenant) -> None:
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        reconciler = RbacProjectionReconciler(async_session_factory)
        await reconciler.run_once()
        first_roles = await _role_permissions(signup_tenant.tenant_id)
        first_grants = await _grant_triples(signup_tenant.tenant_id)

        second = await reconciler.run_once()

        assert second.tenants_reconciled == 0
        assert await _role_permissions(signup_tenant.tenant_id) == first_roles
        assert await _grant_triples(signup_tenant.tenant_id) == first_grants

    async def test_foreign_grant_does_not_borrow_a_same_named_role(
        self, signup_tenant: SignupTenant
    ) -> None:
        """A grant naming another tenant's role must resolve to nothing.

        This is the only fixture that actually exercises the tenant pin in
        Step 2's role lookup. ``signup_tenant`` keeps its OWN role catalog, so
        its own ``tenant_owner`` row is present and available to be matched. If
        the lookup were unpinned, the subquery would resolve the *donor's* role
        name, the join would find ``signup_tenant``'s own ``tenant_owner``, and
        the user would be handed ``*`` - access widening, from a row identity
        never meant to grant it.
        """
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        donor = await _provision_signup_tenant("donor")
        try:
            intruder = await _inject_foreign_grant(signup_tenant, donor)

            await RbacProjectionReconciler(async_session_factory).run_once()

            async with async_session_factory() as session:
                permissions = await RbacRepository(session).resolve_user_permissions(
                    user_id=intruder, tenant_id=signup_tenant.tenant_id
                )
            assert permissions == [], (
                "a grant naming another tenant's role must not resolve to this "
                "tenant's own same-named role"
            )
            # The tenant's real owner is unaffected, so this is a denial of an
            # illegitimate grant and not the reconciler failing to work.
            async with async_session_factory() as session:
                assert sorted(
                    await RbacRepository(session).resolve_user_permissions(
                        user_id=signup_tenant.user_id, tenant_id=signup_tenant.tenant_id
                    )
                ) == ["*", "invitations:send"]
        finally:
            await _delete_tenant(donor.tenant_id)


async def _provision_granted_tenant_without_catalog(
    prefix: str,
) -> tuple[SignupTenant, SignupTenant]:
    """A tenant that has a grant but no role catalog of its own.

    This is the no-progress case. Step 1 copies roles filtered by
    ``tenant_id`` and Step 2 resolves the role through ``roles``, both pinned
    to this tenant, so neither can write anything and
    ``_count_core_user_roles`` stays zero - which is what arms the cooldown.

    This is NOT the same anomaly as a cross-tenant grant, and conflating the
    two hides a bug: with no catalog of its own the tenant has no same-named
    role to match, so the join alone already blocks the grant and Step 2's
    tenant pin is never exercised. That case needs the target to own a
    same-named role, and is covered by
    ``test_foreign_grant_does_not_borrow_a_same_named_role``.

    Returns the stuck tenant and the donor owning the granted role. The donor
    must survive: ``user_roles.role_id`` cascades from ``roles``, so deleting
    it would cascade the grant away and leave no anomaly to reconcile.
    """
    from core.features.rbac.projection_worker import RbacProjectionReconciler

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    donor = await _provision_signup_tenant(prefix)
    # Project the donor so the only remaining gap is `tenant_id` below -
    # otherwise the donor's own rows would mask the anomaly.
    await RbacProjectionReconciler(async_session_factory).run_once()

    async with async_session_factory() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Catalog-less Tenant",
                slug=f"{prefix}-{tenant_id.hex[:8]}",
                plan_tier="free",
                is_active=True,
            )
        )
        await session.commit()
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, password_hash, full_name) "
                "VALUES (:uid, :tid, :email, :hash, :name)"
            ),
            {
                "uid": user_id,
                "tid": tenant_id,
                "email": f"catalogless-{tenant_id.hex[:8]}@signup.skyrict.test",
                "hash": "not-a-real-hash",
                "name": "Catalog-less User",
            },
        )
        donor_role = (
            await session.execute(
                text("SELECT id FROM roles WHERE tenant_id = :tid AND name = 'tenant_owner'"),
                {"tid": donor.tenant_id},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO user_roles (id, tenant_id, user_id, role_id, scope_type, scope_id) "
                "VALUES (gen_random_uuid(), :tid, :uid, :rid, 'tenant', :tid)"
            ),
            {"tid": tenant_id, "uid": user_id, "rid": donor_role},
        )
        await session.commit()
    return SignupTenant(tenant_id=tenant_id, user_id=user_id), donor


async def _inject_foreign_grant(target: SignupTenant, donor: SignupTenant) -> uuid.UUID:
    """Add a user to `target` whose only grant names `donor`'s tenant_owner.

    ``user_roles`` carries three single-column FKs and no composite
    ``(tenant_id, role_id) -> roles(tenant_id, id)``, so a row whose
    denormalised ``tenant_id`` disagrees with its role's tenant is structurally
    legal and identity will keep it.

    ``target`` keeps its OWN role catalog, which is the load-bearing part: the
    join in Step 2 then has a same-named ``tenant_owner`` row sitting right
    there. Without the tenant pin on the role lookup, the subquery resolves the
    donor's role *name*, the join finds ``target``'s own ``tenant_owner``, and
    the user is handed full access to a tenant they were never granted.
    """
    user_id = await _add_user_without_roles(target.tenant_id)
    async with async_session_factory() as session:
        donor_role = (
            await session.execute(
                text("SELECT id FROM roles WHERE tenant_id = :tid AND name = 'tenant_owner'"),
                {"tid": donor.tenant_id},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO user_roles (id, tenant_id, user_id, role_id, scope_type, scope_id) "
                "VALUES (gen_random_uuid(), :tid, :uid, :rid, 'tenant', :tid)"
            ),
            {"tid": target.tenant_id, "uid": user_id, "rid": donor_role},
        )
        await session.commit()
    return user_id


async def _provision_roles_only_tenant(prefix: str) -> tuple[SignupTenant, SignupTenant]:
    """A tenant holding a full role catalog and zero projected grants.

    This is the state a failed Step 2 leaves behind, and it is the state the
    earlier ``core_roles`` anti-join was blind to. Step 1 copies ``roles``
    filtered by ``tenant_id`` and succeeds, so ``core_roles`` is populated;
    Step 2 resolves the grant through the tenant-pinned role-name join, which
    cannot match a grant naming another tenant's role, so ``core_user_roles``
    stays empty. The tenant is locked out while looking fully provisioned.

    Keying the anti-join off ``core_roles`` made this tenant invisible: the
    presence of a role catalog satisfied the query, the tick logged it as
    reconciled, and it was never selected again.

    Returns the stuck tenant and the donor owning the granted role. The donor
    must survive - ``user_roles.role_id`` cascades from ``roles``.
    """
    from core.seed import sync_rbac_from_identity

    target = await _provision_signup_tenant(f"{prefix}-target")
    donor = await _provision_signup_tenant(f"{prefix}-donor")

    # Drop the tenant's own valid grant, then replace it with one that cannot
    # match, so the ONLY thing standing between this tenant and a projection is
    # the tenant pin on Step 2's role lookup.
    async with async_session_factory() as session:
        await session.execute(
            text("DELETE FROM user_roles WHERE tenant_id = :tid"), {"tid": target.tenant_id}
        )
        await session.commit()
    await _inject_foreign_grant(target, donor)

    # Land Step 1's output: role catalog in, grants impossible.
    await sync_rbac_from_identity(target.tenant_id)
    return target, donor


class TestRolesProjectedGrantsMissing:
    """A tenant with a role catalog and no grants must still be detected.

    The gap query keys off ``core_user_roles`` because that is the table
    ``require_permission`` reads. Keying it off ``core_roles`` made a tenant
    whose catalog had landed but whose grants had not look healthy - it was
    logged as reconciled, never selected again, and its owner stayed locked out
    with no warning anywhere.
    """

    async def test_grants_absent_but_roles_present_is_repaired(
        self, signup_tenant: SignupTenant
    ) -> None:
        """The gap is detected and closed when identity's data is sound.

        Constructed by projecting the tenant in full and then deleting only its
        ``core_user_roles`` rows, which is exactly the shape a failed Step 2
        leaves. Under the old ``core_roles`` anti-join this tenant was not
        selected at all, so ``tenants_reconciled`` would be 0 here.
        """
        from core.features.rbac.projection_worker import RbacProjectionReconciler
        from core.seed import sync_rbac_from_identity

        await sync_rbac_from_identity(signup_tenant.tenant_id)
        async with async_session_factory() as session:
            await session.execute(
                text("DELETE FROM core_user_roles WHERE tenant_id = :tid"),
                {"tid": signup_tenant.tenant_id},
            )
            await session.commit()

        roles, grants = await _core_rows(signup_tenant.tenant_id)
        assert roles > 0, "precondition: the role catalog must still be projected"
        assert grants == 0, "precondition: no grants may be projected"

        outcome = await RbacProjectionReconciler(async_session_factory).run_once()

        assert outcome.tenants_reconciled == 1
        assert outcome.tenants_no_progress == 0
        assert await _core_rows(signup_tenant.tenant_id) == (roles, 1)
        async with async_session_factory() as session:
            assert sorted(
                await RbacRepository(session).resolve_user_permissions(
                    user_id=signup_tenant.user_id, tenant_id=signup_tenant.tenant_id
                )
            ) == ["*", "invitations:send"]

    async def test_unmatchable_grant_is_flagged_not_reported_as_repaired(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A catalog that cannot be completed is warned about, not swallowed.

        The tenant keeps being selected - it is still locked out, so the gap
        query must keep seeing it - and the cooldown is what stops the tick
        re-attempting it every few seconds. Under the old ``core_roles``
        anti-join this tenant was invisible, so no warning was ever logged.
        """
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        stuck, donor = await _provision_roles_only_tenant("rolesonly")
        try:
            roles, grants = await _core_rows(stuck.tenant_id)
            assert roles > 0, "precondition: Step 1 must have landed the catalog"
            assert grants == 0, "precondition: Step 2 must have landed nothing"

            reconciler = RbacProjectionReconciler(async_session_factory)
            with caplog.at_level(logging.WARNING, logger="core.features.rbac.projection_worker"):
                outcome = await reconciler.run_once()

            assert outcome.tenants_no_progress == 1
            assert await _core_rows(stuck.tenant_id) == (roles, 0)
            async with async_session_factory() as session:
                assert (
                    await RbacRepository(session).resolve_user_permissions(
                        user_id=stuck.user_id, tenant_id=stuck.tenant_id
                    )
                    == []
                )

            warnings = [
                r for r in caplog.records if r.message == "rbac.projection.tenant_no_progress"
            ]
            assert len(warnings) == 1, "a tenant that cannot be projected must be reported"
            assert warnings[0].tenant_id == str(stuck.tenant_id)
            assert stuck.tenant_id in reconciler._cooldowns
        finally:
            await _delete_tenant(stuck.tenant_id)
            await _delete_tenant(donor.tenant_id)


class TestNoProgressCooldown:
    """A tenant that cannot be projected must not be retried in a hot loop."""

    async def test_tenant_with_grants_but_no_catalog_cools_down(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No grant is invented, a warning names the tenant, and it backs off."""
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        stuck, donor = await _provision_granted_tenant_without_catalog("nocatalog")
        try:
            reconciler = RbacProjectionReconciler(async_session_factory)
            with caplog.at_level(logging.WARNING, logger="core.features.rbac.projection_worker"):
                outcome = await reconciler.run_once()

            assert outcome.tenants_reconciled == 1
            assert outcome.tenants_no_progress == 1
            assert await _core_rows(stuck.tenant_id) == (0, 0)
            async with async_session_factory() as session:
                assert (
                    await RbacRepository(session).resolve_user_permissions(
                        user_id=stuck.user_id, tenant_id=stuck.tenant_id
                    )
                    == []
                )

            warnings = [
                r for r in caplog.records if r.message == "rbac.projection.tenant_no_progress"
            ]
            assert len(warnings) == 1
            assert warnings[0].tenant_id == str(stuck.tenant_id)
        finally:
            await _delete_tenant(stuck.tenant_id)
            await _delete_tenant(donor.tenant_id)

    async def test_stuck_tenant_is_skipped_until_the_cooldown_expires(self) -> None:
        """The backoff is real: one attempt per cooldown window, not per tick."""
        from core.features.rbac import projection_worker
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        stuck, donor = await _provision_granted_tenant_without_catalog("nocatalog")
        try:
            now = 1_000.0
            reconciler = RbacProjectionReconciler(async_session_factory, clock=lambda: now)

            first = await reconciler.run_once()
            assert (first.tenants_reconciled, first.tenants_no_progress) == (1, 1)

            # Still inside the window: the gap is still seen, but not retried.
            now += projection_worker._NO_PROGRESS_COOLDOWN_SECONDS - 1
            second = await reconciler.run_once()
            assert second.gap_tenants == 1
            assert second.tenants_reconciled == 0
            assert second.tenants_cooling_down == 1
            assert second.tenants_no_progress == 0

            # After the window: retried once, and it still cannot make progress.
            now += 1
            third = await reconciler.run_once()
            assert (third.tenants_reconciled, third.tenants_no_progress) == (1, 1)
        finally:
            await _delete_tenant(stuck.tenant_id)
            await _delete_tenant(donor.tenant_id)

    async def test_cooldown_clears_once_the_tenant_projects(
        self, signup_tenant: SignupTenant
    ) -> None:
        """A repaired tenant is reconciled normally, not held back by history."""
        from core.features.rbac import projection_worker
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        now = 1_000.0
        reconciler = RbacProjectionReconciler(async_session_factory, clock=lambda: now)
        reconciler._cooldowns[signup_tenant.tenant_id] = (
            now + projection_worker._NO_PROGRESS_COOLDOWN_SECONDS
        )

        # Inside the window it is skipped...
        assert (await reconciler.run_once()).tenants_cooling_down == 1
        # ...and reconciling it clears the cooldown rather than leaving it set.
        now += projection_worker._NO_PROGRESS_COOLDOWN_SECONDS
        assert (await reconciler.run_once()).tenants_reconciled == 1
        assert signup_tenant.tenant_id not in reconciler._cooldowns


class TestFailureIsolation:
    """One bad tenant must not stop the pass, the loop, or the process."""

    async def test_failing_tenant_is_logged_and_the_pass_continues(
        self,
        signup_tenant: SignupTenant,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The failure is logged with a traceback and swallowed at the tenant."""
        import core.features.rbac.projection_worker as worker
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        neighbour = await _provision_signup_tenant("resilient")
        calls: list[uuid.UUID] = []
        real = worker.sync_rbac_from_identity

        async def flaky(tenant_id: uuid.UUID | None = None) -> None:
            calls.append(tenant_id)  # type: ignore[arg-type]
            if tenant_id == neighbour.tenant_id:
                raise RuntimeError("simulated database failure")
            await real(tenant_id)

        monkeypatch.setattr(worker, "sync_rbac_from_identity", flaky)

        with caplog.at_level(logging.ERROR, logger="core.features.rbac.projection_worker"):
            outcome = await RbacProjectionReconciler(async_session_factory).run_once()

        assert neighbour.tenant_id in calls
        assert signup_tenant.tenant_id in calls
        assert outcome.tenants_failed == 1
        assert outcome.tenants_reconciled == 1
        assert await _core_rows(signup_tenant.tenant_id) != (0, 0)
        assert await _core_rows(neighbour.tenant_id) == (0, 0)

        failures = [r for r in caplog.records if r.message == "rbac.projection.tenant_failed"]
        assert len(failures) == 1
        assert failures[0].tenant_id == str(neighbour.tenant_id)
        assert failures[0].exc_info is not None

        await _delete_tenant(neighbour.tenant_id)

    async def test_scoped_run_projects_only_the_named_tenants_pending_grant(
        self, signup_tenant: SignupTenant
    ) -> None:
        """A scoped run must not project another tenant's outstanding grant.

        The tenant predicate on Step 2 is what bounds the insert set to the
        tenant that was asked for. Without it, every ``user_roles`` row in the
        table is joined against whatever ``core_roles`` exist, so a partly
        projected tenant gets finished as a side effect of reconciling an
        unrelated one.

        The grant created here is *correct* - it names a role the tenant
        really owns - so nothing about it is a safety violation. That is the
        point: this test pins the scoping contract (do what you were asked, and
        no more) rather than a security property, which is what the tenant pin
        on the role lookup covers.
        """
        from core.seed import sync_rbac_from_identity

        neighbour = await _provision_signup_tenant("pending")
        try:
            # Project the neighbour's role catalog but not its owner's grant,
            # which is the partly-projected state the scoping contract is about.
            async with async_session_factory() as session:
                await session.execute(
                    text(
                        "INSERT INTO core_roles (id, tenant_id, name, permissions, is_system_role) "
                        "SELECT r.id, r.tenant_id, r.name, r.permissions, r.is_system_role "
                        "FROM roles r WHERE r.tenant_id = :tid"
                    ),
                    {"tid": neighbour.tenant_id},
                )
                await session.commit()
            roles, grants = await _core_rows(neighbour.tenant_id)
            assert (roles, grants) == (6, 0), "fixture should be roles-only"

            await sync_rbac_from_identity(signup_tenant.tenant_id)

            assert await _core_rows(neighbour.tenant_id) == (6, 0), (
                "reconciling one tenant must not project another's pending grant"
            )
        finally:
            await _delete_tenant(neighbour.tenant_id)

    async def test_loop_survives_a_failing_pass_and_stops_cleanly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pass that raises outright must not kill the background loop.

        Per-tenant failures are already contained inside ``run_once``; this
        covers the failure that escapes it - the gap query itself failing,
        e.g. the database going away - and asserts the loop keeps running and
        still shuts down cleanly.
        """
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        real = RbacProjectionReconciler._gap_tenant_ids
        attempts = 0

        async def broken(_self: RbacProjectionReconciler) -> list[uuid.UUID]:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("simulated database failure")

        monkeypatch.setattr(RbacProjectionReconciler, "_gap_tenant_ids", broken)

        reconciler = RbacProjectionReconciler(async_session_factory)
        reconciler.start()
        deadline = asyncio.get_running_loop().time() + 10.0
        while attempts == 0 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert attempts == 1
        assert reconciler.running is True

        monkeypatch.setattr(RbacProjectionReconciler, "_gap_tenant_ids", real)
        task = reconciler._task
        await reconciler.stop(timeout=10.0)

        assert not reconciler.running
        assert attempts == 1, "stop() must interrupt the sleep, not run a pass"
        # Cancelling the task also ends it, so `not running` alone cannot tell a
        # graceful stop from the timeout path. A real shutdown wakes the sleep
        # through the stop event and lets the loop finish its own pass; only the
        # cancel path leaves the task cancelled. Without this assertion, removing
        # the stop signal still passes, and every shutdown silently becomes a
        # timeout-then-cancel that holds the loop open for the full timeout.
        assert task is not None
        assert task.cancelled() is False, "stop() should wake the loop, not cancel it"

    async def test_stop_is_idempotent_without_a_task(self) -> None:
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        reconciler = RbacProjectionReconciler(async_session_factory)
        await reconciler.stop()
        assert not reconciler.running


class TestRlsCapabilityGuard:
    """The guard that stops this worker degrading into a silent no-op.

    ``core_roles`` and ``core_user_roles`` are RLS-protected on
    ``tenant_id = current_tenant_id()`` and a background task has no request
    tenant, so the tick depends on the database role bypassing RLS. If it stops
    doing that, every tick reports healthy while repairing nothing - the failure
    mode this guard exists to prevent. The probe requires capability on **both**
    tables, because ownership is per-table and the worker reads both.
    """

    # A literal, not a parameter: it is interpolated into DDL, and there is no
    # reason for it to be anything else.
    PROBE_ROLE = "skyrict_probe_rls"
    # Distinct from PROBE_ROLE: this fixture reassigns table ownership, so it
    # must never share a role with the fixture that only probes.
    PROBE_OWNER_ROLE = "skyrict_probe_owner"

    @pytest.fixture
    async def restricted_role(self) -> AsyncGenerator[str, None]:
        """A role that cannot bypass RLS and owns none of core's tables."""
        async with async_session_factory() as session:
            try:
                await session.execute(text(f'CREATE ROLE "{self.PROBE_ROLE}" NOLOGIN'))
            except DBAPIError as exc:
                await session.rollback()
                pytest.skip(f"insufficient privilege to create a probe role: {exc}")
            await session.commit()
        try:
            yield self.PROBE_ROLE
        finally:
            async with async_session_factory() as session:
                await session.execute(text(f'DROP ROLE IF EXISTS "{self.PROBE_ROLE}"'))
                await session.commit()

    async def test_probe_distinguishes_a_role_that_cannot_bypass(
        self, restricted_role: str
    ) -> None:
        from core.features.rbac.projection_worker import _CAN_BYPASS_RLS_SQL

        async with async_session_factory() as session:
            # Core's own role bypasses RLS, so the worker runs in production.
            assert await session.scalar(_CAN_BYPASS_RLS_SQL) is True

            await session.execute(text(f'SET ROLE "{restricted_role}"'))
            try:
                # A role with neither BYPASSRLS nor table ownership would see
                # nothing, so the probe must say so rather than return true.
                assert await session.scalar(_CAN_BYPASS_RLS_SQL) is False
            finally:
                await session.execute(text("RESET ROLE"))

    @pytest.fixture
    async def owns_core_roles_only(self) -> AsyncGenerator[str, None]:
        """A role that owns ``core_roles`` but NOT ``core_user_roles``.

        Ownership is per-table, so this is a real configuration rather than a
        contrived one: a role can satisfy a probe that inspects a single table
        while its reads of the other are still filtered by RLS. The worker
        reads both - the gap query and the progress count - so the probe has to
        require both. Table ownership is restored on teardown because the rest
        of the suite runs against these same tables.
        """
        async with async_session_factory() as session:
            try:
                await session.execute(text(f'CREATE ROLE "{self.PROBE_OWNER_ROLE}" NOLOGIN'))
            except DBAPIError as exc:
                await session.rollback()
                pytest.skip(f"insufficient privilege to create a probe role: {exc}")
            owner = (
                await session.execute(
                    text(
                        "SELECT pg_get_userbyid(relowner) FROM pg_class "
                        "WHERE oid = 'core_roles'::regclass"
                    )
                )
            ).scalar_one()
            await session.execute(
                text(f'ALTER TABLE core_roles OWNER TO "{self.PROBE_OWNER_ROLE}"')
            )
            await session.commit()
        try:
            yield self.PROBE_OWNER_ROLE
        finally:
            async with async_session_factory() as session:
                await session.execute(text(f'ALTER TABLE core_roles OWNER TO "{owner}"'))
                await session.commit()
                await session.execute(text(f'DROP ROLE IF EXISTS "{self.PROBE_OWNER_ROLE}"'))
                await session.commit()

    async def test_probe_requires_both_rbac_tables(self, owns_core_roles_only: str) -> None:
        """Owning one of the two tables must not be reported as sufficient."""
        from core.features.rbac.projection_worker import _CAN_BYPASS_RLS_SQL

        async with async_session_factory() as session:
            await session.execute(text(f'SET ROLE "{owns_core_roles_only}"'))
            try:
                # If this returned true the worker would start, and its reads of
                # core_user_roles would be RLS-filtered: every tenant would look
                # unprojected, so every tick would select every tenant.
                assert await session.scalar(_CAN_BYPASS_RLS_SQL) is False
            finally:
                await session.execute(text("RESET ROLE"))

    async def test_loop_refuses_to_run_when_rls_would_hide_the_gap(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        async def cannot(_self: RbacProjectionReconciler) -> bool:
            return False

        monkeypatch.setattr(RbacProjectionReconciler, "_can_bypass_rls", cannot)

        reconciler = RbacProjectionReconciler(async_session_factory)
        with caplog.at_level(logging.ERROR, logger="core.features.rbac.projection_worker"):
            reconciler.start()
            deadline = asyncio.get_running_loop().time() + 10.0
            while reconciler.running and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.01)

        assert not reconciler.running
        assert [r for r in caplog.records if r.message == "rbac.projection.rls_not_bypassable"]


class TestLifespanWiring:
    """Boot-path wiring, including the documented kill switch."""

    @staticmethod
    @asynccontextmanager
    async def _lifespan(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> AsyncIterator:
        """Run the real lifespan with the flag forced, yielding inside it."""
        from core.api.lifespan import lifespan
        from core.core.config import Environment, settings
        from core.main import app

        monkeypatch.setattr(settings, "RBAC_PROJECTION_ENABLED", enabled)
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        async with lifespan(app):
            yield app.state.rbac_projection_reconciler

    async def test_reconciler_starts_when_enabled(
        self, migrated_schema: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The enabled default actually starts a running background task."""
        async with self._lifespan(monkeypatch, enabled=True) as reconciler:
            assert reconciler is not None
            assert reconciler.running is True

    async def test_kill_switch_stops_it_starting(
        self, migrated_schema: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With the flag off, no task exists - the documented off switch."""
        async with self._lifespan(monkeypatch, enabled=False) as reconciler:
            assert reconciler is None

    async def test_disabled_under_the_test_environment(
        self, migrated_schema: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Integration tests drive run_once() directly, so the loop stays off."""
        from contextlib import AsyncExitStack

        from core.api.lifespan import lifespan
        from core.core.config import Environment, settings
        from core.main import app

        monkeypatch.setattr(settings, "RBAC_PROJECTION_ENABLED", True)
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.TEST)
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(lifespan(app))
            assert app.state.rbac_projection_reconciler is None
