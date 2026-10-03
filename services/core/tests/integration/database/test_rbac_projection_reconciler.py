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

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select, text

from core.db.rbac import RbacRepository, grants_permission
from core.db.session import async_session_factory
from core.models.core_role import CoreRoleModel
from core.models.core_user_role import CoreUserRoleModel
from core.models.tenant import TenantModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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


@pytest.fixture
async def signup_tenant(migrated_schema: None) -> AsyncGenerator[SignupTenant, None]:
    """A tenant whose identity rows exist and whose core rows do not yet.

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
                name="Signup Tenant",
                slug=f"signup-{tenant_id.hex[:8]}",
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

    try:
        yield SignupTenant(tenant_id=tenant_id, user_id=user_id)
    finally:
        async with async_session_factory() as session:
            await session.execute(
                text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id}
            )
            await session.commit()


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