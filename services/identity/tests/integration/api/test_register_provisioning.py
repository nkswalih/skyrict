"""Integration tests for self-service tenant provisioning (SKY-30).

Proves the onboarding wizard contract: a successful organization step
provisions tenant + 5 system roles + verified owner + grant; a mid-transaction
failure leaves ZERO orphan rows; a taken email is rejected with a 409; and the
provisioned owner can log in immediately (is_verified is set at provisioning).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, func, select

from identity.db.session import async_session_factory
from identity.models.role import RoleModel
from identity.models.tenant import TenantModel
from identity.models.user import UserModel
from identity.models.user_role import UserRoleModel
from skyrict_common.exceptions import RateLimitExceededError
from tests.integration.api.wizard import (
    DEFAULT_PASSWORD,
    provision_tenant,
    wizard_login,
    wizard_send_code,
    wizard_set_password,
    wizard_start,
    wizard_verify_code,
)

if TYPE_CHECKING:
    from httpx import AsyncClient

SYSTEM_ROLE_NAMES = {
    "tenant_owner",
    "organization_admin",
    "department_manager",
    "standard_user",
    "auditor",
    "employee_self_service",
}

pytestmark = pytest.mark.integration


async def _cleanup_tenant(slug: str) -> None:
    """Remove a provisioned tenant (cascades to users/roles/grants/audit)."""
    async with async_session_factory() as session:
        await session.execute(delete(TenantModel).where(TenantModel.slug == slug))
        await session.commit()


class TestProvisioning:
    async def test_wizard_provisions_tenant_owner_and_five_system_roles(
        self, client: AsyncClient
    ) -> None:
        tenant = await provision_tenant(client)
        try:
            async with async_session_factory() as session:
                row = await session.scalar(
                    select(TenantModel).where(TenantModel.slug == tenant["slug"])
                )
                assert row is not None
                assert row.plan_tier == "professional"

                roles = (
                    await session.scalars(select(RoleModel).where(RoleModel.tenant_id == row.id))
                ).all()
                assert len(roles) == 6
                by_name = {role.name: role for role in roles}
                assert set(by_name) == SYSTEM_ROLE_NAMES
                assert all(role.is_system_role for role in roles)
                assert "*" in by_name["tenant_owner"].permissions

                user = await session.scalar(
                    select(UserModel).where(UserModel.email == tenant["email"])
                )
                assert user is not None
                assert user.tenant_id == row.id
                assert user.is_verified is True

                grant = await session.scalar(
                    select(UserRoleModel).where(
                        UserRoleModel.user_id == user.id,
                        UserRoleModel.role_id == by_name["tenant_owner"].id,
                    )
                )
                assert grant is not None
                assert grant.scope_id == row.id
        finally:
            await _cleanup_tenant(tenant["slug"])

    async def test_wizard_failure_leaves_no_orphan_rows(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from identity.features.roles.repository import RoleRepository

        async def boom(self: RoleRepository, role: object) -> object:
            raise RuntimeError("simulated mid-transaction failure")

        monkeypatch.setattr(RoleRepository, "create", boom)

        email = f"prov-{uuid.uuid4().hex[:8]}@test.com"
        org = f"Prov Corp {uuid.uuid4().hex[:8]}"
        slug = org.lower().replace(" ", "-")

        await wizard_start(client, email=email)
        code = await wizard_send_code(client, email=email)
        vt = await wizard_verify_code(client, email=email, code=code)
        await wizard_set_password(
            client, email=email, verification_token=vt, password=DEFAULT_PASSWORD
        )

        response = await client.post(
            "/api/v1/auth/signup/organization",
            json={
                "email": email,
                "verificationToken": vt,
                "planId": "professional",
                "companyName": org,
                "industry": "Technology",
                "workspaceSlug": slug,
                "ownerFullName": "Provisioning User",
            },
        )
        assert response.status_code == 500

        async with async_session_factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(TenantModel).where(TenantModel.slug == slug)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(UserModel).where(UserModel.email == email)
                )
                == 0
            )

    async def test_duplicate_email_rejected_with_409(self, client: AsyncClient) -> None:
        from identity.core.security import hash_password
        from identity.features.auth.verification_store import VerificationStore

        email = f"prov-{uuid.uuid4().hex[:8]}@test.com"
        first = await provision_tenant(client, email=email)
        try:
            # A second signup for the same email would hit the OTP resend
            # cooldown, so model the session directly: a fresh verification
            # token bound to this email with a password hash set, then walk
            # the org step that must refuse to re-provision the email.
            vt = uuid.uuid4().hex
            store = VerificationStore()
            await store.set_verification_token(vt, email, hash_password(DEFAULT_PASSWORD))
            await wizard_start(client, email=email)

            second = await client.post(
                "/api/v1/auth/signup/organization",
                json={
                    "email": email,
                    "verificationToken": vt,
                    "planId": "professional",
                    "companyName": "Second Corp",
                    "industry": "Technology",
                    "workspaceSlug": f"dup-{uuid.uuid4().hex[:8]}",
                    "ownerFullName": "Second Owner",
                },
            )
            assert second.status_code == 409
            assert second.json()["type"].endswith("/user-already-exists")

            async with async_session_factory() as session:
                count = await session.scalar(
                    select(func.count()).select_from(UserModel).where(UserModel.email == email)
                )
                assert count == 1
        finally:
            await _cleanup_tenant(first["slug"])


class TestAuthPosture:
    async def test_mfa_required_for_tenant_owner_without_mfa(self, client: AsyncClient) -> None:
        tenant = await provision_tenant(client)
        try:
            login = await client.post(
                "/api/v1/auth/login",
                headers={"X-Tenant-Slug": tenant["slug"]},
                json={"email": tenant["email"], "password": DEFAULT_PASSWORD},
            )
            assert login.status_code == 200
            assert login.json()["data"]["mfa_required"] is True
            assert login.json()["data"]["access_token"]
        finally:
            await _cleanup_tenant(tenant["slug"])


class TestCustomRoles:
    async def test_create_and_list_custom_role(self, client: AsyncClient) -> None:
        tenant = await provision_tenant(client)
        creds = await wizard_login(
            client, slug=tenant["slug"], email=tenant["email"], password=tenant["password"]
        )
        headers = {
            "X-Tenant-Slug": tenant["slug"],
            "Authorization": f"Bearer {creds['token']}",
        }
        try:
            created = await client.post(
                "/api/v1/roles",
                headers=headers,
                json={"name": "custom_ops", "permission_keys": ["users:read", "audit:read"]},
            )
            assert created.status_code == 200
            created_data = created.json()["data"]
            assert created_data["name"] == "custom_ops"
            assert created_data["is_system_role"] is False

            listed = await client.get("/api/v1/roles", headers=headers)
            assert listed.status_code == 200
            names = {role["name"] for role in listed.json()["data"]}
            assert "custom_ops" in names
            assert names >= SYSTEM_ROLE_NAMES

            reserved = await client.post(
                "/api/v1/roles",
                headers=headers,
                json={"name": "tenant_owner", "permission_keys": ["users:read"]},
            )
            assert reserved.status_code == 422
        finally:
            await _cleanup_tenant(tenant["slug"])


class TestRateLimit:
    async def test_signup_start_rate_limited(self, client: AsyncClient) -> None:
        from identity.api.deps import get_rate_limiter
        from identity.main import app

        class DenyLimiter:
            async def enforce(self, *, key: str, limit: int, window_seconds: int) -> None:
                raise RateLimitExceededError("rate limited")

        app.dependency_overrides[get_rate_limiter] = lambda: DenyLimiter()
        try:
            response = await client.post("/api/v1/auth/signup/start", json={"email": "rl@test.com"})
            assert response.status_code == 429
            assert response.json()["type"].endswith("/rate-limit-exceeded")
        finally:
            app.dependency_overrides.pop(get_rate_limiter, None)
