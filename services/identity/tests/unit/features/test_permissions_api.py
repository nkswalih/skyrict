"""Unit tests for the permissions catalog API (GET /permissions) and DoD validation.

Uses a dedicated FastAPI app (built via create_app) with dependency overrides so the
module-level identity.main app is never mutated. Verifies:
  - GET /permissions returns 200 with 19 modules, 39 unique keys, union == CATALOG
  - POST /roles with invalid key -> 422, error detail names the key
  - POST /roles with valid keys -> 200, response permissions fully resolved
  - POST /roles with old 'permissions' field -> 422 (extra='forbid' proof)
  - POST /roles with empty permission_keys -> 422 (min_length proof)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import httpx
import pytest

if TYPE_CHECKING:
    from fastapi import FastAPI

import identity.api.middleware as middleware_module
from identity.core.permissions import CATALOG
from identity.main import create_app


@pytest.fixture
def test_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # Stub the middleware's tenant lookup so these tests run without a database.
    now = datetime.now(UTC)
    fake_tenant = SimpleNamespace(
        id=uuid.uuid4(),
        name="Default Org",
        slug="default",
        is_active=True,
        plan_tier="free",
        industry=None,
        billing_address=None,
        onboarding_completed_at=None,
        created_at=now,
        updated_at=now,
    )

    class _FakeResult:
        def __init__(self, tenant: object) -> None:
            self._tenant = tenant

        def scalar_one_or_none(self) -> object:
            return self._tenant

    class _FakeSession:
        async def execute(self, stmt: object) -> _FakeResult:
            return _FakeResult(fake_tenant)

    @asynccontextmanager
    async def _noop_db_session():
        yield _FakeSession()

    monkeypatch.setattr(middleware_module, "async_session_factory", _noop_db_session)

    # Build the real app with all exception handlers
    application = create_app()

    # Override auth and service dependencies for unit testing
    from identity.api.deps import (
        get_current_user,
        get_role_repo,
        get_roles_service,
        get_user_repo,
    )

    fake_user = {
        "user_id": uuid.uuid4(),
        "tenant_id": fake_tenant.id,
        "token_payload": {"sub": str(uuid.uuid4())},
    }

    class FakeRoleRepo:
        def __init__(self) -> None:
            self.roles = {}
            self.grants = []
            self.deleted = []

        async def create(self, role):
            role.id = uuid.uuid4()
            self.roles[role.id] = role
            return role

        async def get_by_id(self, role_id):
            return self.roles.get(uuid.UUID(str(role_id)))

        async def get_by_name(self, tenant_id, name):
            for role in self.roles.values():
                if role.name == name and str(role.tenant_id) == str(tenant_id):
                    return role
            return None

        async def list_by_tenant(self, tenant_id, *, offset=0, limit=20):
            roles = [r for r in self.roles.values() if str(r.tenant_id) == str(tenant_id)]
            roles.sort(key=lambda r: r.name)
            return roles[offset : offset + limit]

        async def grant_to_user(self, *, user_id, role_id, tenant_id, scope_id, scope_type):
            self.grants.append(
                {
                    "user_id": uuid.UUID(str(user_id)),
                    "role_id": uuid.UUID(str(role_id)),
                    "tenant_id": uuid.UUID(str(tenant_id)),
                    "scope_id": uuid.UUID(str(scope_id)),
                    "scope_type": scope_type,
                }
            )

        async def update(self, role):
            if role.id is not None:
                self.roles[role.id] = role
            return role

        async def delete(self, role_id):
            role_uuid = uuid.UUID(str(role_id))
            self.deleted.append(role_uuid)
            self.roles.pop(role_uuid, None)

        async def grant_exists(self, user_id, role_id, scope_type, scope_id):
            return any(
                grant["user_id"] == uuid.UUID(str(user_id))
                and grant["role_id"] == uuid.UUID(str(role_id))
                and grant["scope_type"] == scope_type
                and grant["scope_id"] == uuid.UUID(str(scope_id))
                for grant in self.grants
            )

        async def get_roles_for_user(self, user_id, tenant_id):
            names = []
            for grant in self.grants:
                if grant["user_id"] == uuid.UUID(str(user_id)) and grant["tenant_id"] == uuid.UUID(
                    str(tenant_id)
                ):
                    role = self.roles.get(grant["role_id"])
                    if role is not None:
                        names.append(role.name)
            return names

        async def get_permissions_for_user(self, user_id, tenant_id):
            permissions = set()
            for grant in self.grants:
                if grant["user_id"] == uuid.UUID(str(user_id)) and grant["tenant_id"] == uuid.UUID(
                    str(tenant_id)
                ):
                    role = self.roles.get(grant["role_id"])
                    if role is not None:
                        permissions.update(role.permissions)
            return permissions

    fake_repo = FakeRoleRepo()

    # Pre-grant roles:write permission to the fake user so it can call POST /roles
    role_id = uuid.uuid4()
    fake_repo.roles[role_id] = SimpleNamespace(
        id=role_id,
        name="test_admin",
        permissions=["roles:write"],
        is_system_role=False,
        tenant_id=fake_tenant.id,
    )
    fake_repo.grants.append(
        {
            "user_id": fake_user["user_id"],
            "role_id": role_id,
            "tenant_id": fake_tenant.id,
            "scope_id": fake_tenant.id,
            "scope_type": "tenant",
        }
    )

    async def _fake_get_current_user():
        return fake_user

    async def _fake_get_user_repo():
        return AsyncMock()

    async def _fake_get_role_repo():
        return fake_repo

    async def _fake_get_roles_service():
        from identity.features.roles.service import RoleManagementService

        return RoleManagementService(fake_repo)

    application.dependency_overrides[get_current_user] = _fake_get_current_user
    application.dependency_overrides[get_user_repo] = _fake_get_user_repo
    application.dependency_overrides[get_role_repo] = _fake_get_role_repo
    application.dependency_overrides[get_roles_service] = _fake_get_roles_service

    return application


@pytest.fixture
async def http_client(test_app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Tenant-Slug": "default"}
    ) as client:
        yield client


class TestPermissionsCatalog:
    async def test_get_permissions_catalog_structure(self, http_client: httpx.AsyncClient) -> None:
        """GET /permissions returns all permission modules and keys from CATALOG."""
        response = await http_client.get("/api/v1/permissions")
        assert response.status_code == 200

        body = response.json()
        assert body["message"] == "Permission catalog retrieved"
        data = body["data"]
        assert "modules" in data

        modules = data["modules"]
        assert len(modules) == 21

        # Collect all keys from modules
        all_keys = []
        module_keys_set = set()
        for module in modules:
            assert "key" in module
            assert "label" in module
            assert "permissions" in module
            for perm in module["permissions"]:
                assert "key" in perm
                assert "description" in perm
                all_keys.append(perm["key"])
                module_keys_set.add(perm["key"])

        # 44 unique keys (erp.ai.invoke + erp.leave.self + erp.hr.ai.*
        # + erp.inventory.ai.approve since SKY-68)
        assert len(all_keys) == 44
        assert len(module_keys_set) == 44

        # Union equals CATALOG
        catalog_set = set(CATALOG)
        assert module_keys_set == catalog_set

        # Each module has stable key + label
        expected_module_keys = {
            "user",
            "role",
            "tenant",
            "session",
            "audit",
            "security",
            "settings",
            "erp",
            "erp_crm",
            "erp_sales",
            "erp_inventory",
            "erp_finance",
            "erp_hr",
            "erp_payroll",
            "erp_ai",
            "erp_hr_ai",
            "erp_leave_self",
            "agents",
            "intelligence",
            "billing",
            "invitations",
        }
        actual_module_keys = {m["key"] for m in modules}
        assert actual_module_keys == expected_module_keys


class TestGetMyRoles:
    async def test_returns_roles_and_permissions_for_current_user(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """GET /roles/me returns the authenticated user's roles and permissions."""
        response = await http_client.get("/api/v1/roles/me")
        assert response.status_code == 200

        body = response.json()
        assert body["message"] == "Roles retrieved"
        assert body["data"]["roles"] == ["test_admin"]
        assert body["data"]["permissions"] == ["roles:write"]


class TestRoleCreateDoD:
    async def test_invalid_key_returns_422(self, http_client: httpx.AsyncClient) -> None:
        """POST /roles with invalid key -> 422, error detail names the key."""
        response = await http_client.post(
            "/api/v1/roles",
            json={"name": "test_role", "permission_keys": ["invalid:key"]},
        )
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body
        # The error should mention the invalid key
        assert "invalid:key" in str(body).lower() or "unknown permission" in str(body).lower()

    async def test_valid_keys_returns_200(self, http_client: httpx.AsyncClient) -> None:
        """POST /roles with valid keys -> 200, response permissions fully resolved."""
        response = await http_client.post(
            "/api/v1/roles",
            json={"name": "test_role", "permission_keys": ["users:read", "roles:read"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Role created"
        data = body["data"]
        assert data["name"] == "test_role"
        assert set(data["permissions"]) == {"users:read", "roles:read"}
        assert data["is_system_role"] is False

    async def test_old_permissions_field_returns_422(self, http_client: httpx.AsyncClient) -> None:
        """POST /roles with old 'permissions' field -> 422 (extra='forbid' proof)."""
        response = await http_client.post(
            "/api/v1/roles",
            json={"name": "test_role", "permissions": ["users:read"]},
        )
        assert response.status_code == 422
        body = response.json()
        # Pydantic extra='forbid' should reject the unknown field
        assert (
            "extra" in str(body).lower()
            or "unexpected" in str(body).lower()
            or "forbid" in str(body).lower()
        )

    async def test_empty_permission_keys_returns_422(self, http_client: httpx.AsyncClient) -> None:
        """POST /roles with empty permission_keys -> 422 (min_length proof)."""
        response = await http_client.post(
            "/api/v1/roles",
            json={"name": "test_role", "permission_keys": []},
        )
        assert response.status_code == 422
        body = response.json()
        # Pydantic min_length=1 should reject empty list
        assert (
            "min_length" in str(body).lower()
            or "at least" in str(body).lower()
            or "empty" in str(body).lower()
            or "length" in str(body).lower()
        )
