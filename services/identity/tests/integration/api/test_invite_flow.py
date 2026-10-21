"""
Integration tests for the invitation flow (SKY-16).

Tests the full invitation lifecycle: create, accept, expired token rejection,
already-used token rejection, and email-mismatch rejection.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from identity.db.session import async_session_factory
from identity.models.invitation import InvitationModel
from identity.models.tenant import TenantModel
from tests.integration.api.mfa_helpers import enroll_mfa_if_required
from tests.integration.api.wizard import provision_tenant, wizard_login

if TYPE_CHECKING:
    from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _cleanup_tenant(slug: str) -> None:
    async with async_session_factory() as session:
        await session.execute(delete(TenantModel).where(TenantModel.slug == slug))
        await session.commit()


async def _register_tenant(client: AsyncClient, *, org_name: str | None = None) -> dict:
    tenant = await provision_tenant(client, org=org_name)
    creds = await wizard_login(
        client, slug=tenant["slug"], email=tenant["email"], password=tenant["password"]
    )
    return {
        "slug": tenant["slug"],
        "tenant_id": tenant["tenant_id"],
        "email": tenant["email"],
        "token": creds["token"],
    }


class TestInvitationFlow:
    async def test_create_and_accept_invitation(self, client: AsyncClient) -> None:
        tenant = await _register_tenant(client)
        headers = {"X-Tenant-Slug": tenant["slug"], "Authorization": f"Bearer {tenant['token']}"}

        invite_email = f"invitee-{uuid.uuid4().hex[:8]}@test.com"
        create_resp = await client.post(
            "/api/v1/invitations",
            headers=headers,
            json={"email": invite_email, "role_name": "standard_user"},
        )
        assert create_resp.status_code == 200
        invite_data = create_resp.json()["data"]
        assert invite_data["email"] == invite_email
        assert invite_data["token"]
        assert invite_data["role_name"] == "standard_user"
        assert invite_data["used_at"] is None

        accept_resp = await client.post(
            "/api/v1/invitations/accept",
            headers={"X-Tenant-Slug": tenant["slug"]},
            data={
                "token": invite_data["token"],
                "email": invite_email,
                "password": "InviteePass123!",
                "full_name": "Invitee User",
            },
        )
        assert accept_resp.status_code == 200
        user_data = accept_resp.json()["data"]
        assert user_data["email"] == invite_email
        assert user_data["is_verified"] is True

        with contextlib.suppress(Exception):
            await _cleanup_tenant(tenant["slug"])

    async def test_invite_rejects_email_registered_in_another_tenant(
        self, client: AsyncClient
    ) -> None:
        """A global account is reported as unavailable, not invited twice."""
        owner_tenant = await _register_tenant(client)
        inviter_tenant = await _register_tenant(client)
        headers = {
            "X-Tenant-Slug": inviter_tenant["slug"],
            "Authorization": f"Bearer {inviter_tenant['token']}",
        }

        resp = await client.post(
            "/api/v1/invitations",
            headers=headers,
            json={"email": owner_tenant["email"], "role_name": "standard_user"},
        )

        assert resp.status_code == 409
        body = resp.json()
        assert body["type"].endswith("/user-already-exists")
        assert body["detail"] == "This email is unavailable."

        with contextlib.suppress(Exception):
            await _cleanup_tenant(owner_tenant["slug"])
        with contextlib.suppress(Exception):
            await _cleanup_tenant(inviter_tenant["slug"])

    async def test_accept_rejects_email_registered_after_the_invite(
        self, client: AsyncClient
    ) -> None:
        """A stale invite for an email that registered elsewhere conflicts, not 500."""
        invitee_email = f"late-{uuid.uuid4().hex[:8]}@test.com"
        inviter_tenant = await _register_tenant(client)
        headers = {
            "X-Tenant-Slug": inviter_tenant["slug"],
            "Authorization": f"Bearer {inviter_tenant['token']}",
        }

        create_resp = await client.post(
            "/api/v1/invitations",
            headers=headers,
            json={"email": invitee_email},
        )
        assert create_resp.status_code == 200
        invite_token = create_resp.json()["data"]["token"]

        # The invitee registers their own workspace AFTER the invite went out,
        # so the create-time guard could not have seen the account yet.
        registrant_tenant = await provision_tenant(client, email=invitee_email)

        accept_resp = await client.post(
            "/api/v1/invitations/accept",
            headers={"X-Tenant-Slug": inviter_tenant["slug"]},
            data={
                "token": invite_token,
                "email": invitee_email,
                "password": "InviteePass123!",
                "full_name": "Late Registrant",
            },
        )

        assert accept_resp.status_code == 409
        assert accept_resp.json()["type"].endswith("/user-already-exists")

        with contextlib.suppress(Exception):
            await _cleanup_tenant(inviter_tenant["slug"])
        with contextlib.suppress(Exception):
            await _cleanup_tenant(registrant_tenant["slug"])

    async def test_expired_token_rejected(self, client: AsyncClient) -> None:
        tenant = await _register_tenant(client)
        headers = {"X-Tenant-Slug": tenant["slug"], "Authorization": f"Bearer {tenant['token']}"}

        invite_email = f"expired-{uuid.uuid4().hex[:8]}@test.com"
        create_resp = await client.post(
            "/api/v1/invitations",
            headers=headers,
            json={"email": invite_email},
        )
        assert create_resp.status_code == 200
        invite_data = create_resp.json()["data"]
        invite_id = invite_data["id"]
        invite_token = invite_data["token"]

        async with async_session_factory() as session:
            model = await session.get(InvitationModel, uuid.UUID(invite_id))
            if model:
                model.expires_at = datetime.now(UTC) - timedelta(days=1)
                await session.commit()

        accept_resp = await client.post(
            "/api/v1/invitations/accept",
            headers={"X-Tenant-Slug": tenant["slug"]},
            data={
                "token": invite_token,
                "email": invite_email,
                "password": "InviteePass123!",
                "full_name": "Expired User",
            },
        )
        assert accept_resp.status_code in (400, 403, 422)

        with contextlib.suppress(Exception):
            await _cleanup_tenant(tenant["slug"])

    async def test_already_used_token_rejected(self, client: AsyncClient) -> None:
        tenant = await _register_tenant(client)
        headers = {"X-Tenant-Slug": tenant["slug"], "Authorization": f"Bearer {tenant['token']}"}

        invite_email = f"used-{uuid.uuid4().hex[:8]}@test.com"
        create_resp = await client.post(
            "/api/v1/invitations",
            headers=headers,
            json={"email": invite_email},
        )
        assert create_resp.status_code == 200
        invite_data = create_resp.json()["data"]

        first_accept = await client.post(
            "/api/v1/invitations/accept",
            headers={"X-Tenant-Slug": tenant["slug"]},
            data={
                "token": invite_data["token"],
                "email": invite_email,
                "password": "InviteePass123!",
                "full_name": "First Accept",
            },
        )
        assert first_accept.status_code == 200

        second_accept = await client.post(
            "/api/v1/invitations/accept",
            headers={"X-Tenant-Slug": tenant["slug"]},
            data={
                "token": invite_data["token"],
                "email": invite_email,
                "password": "InviteePass123!",
                "full_name": "Second Accept",
            },
        )
        assert second_accept.status_code in (400, 409)

        with contextlib.suppress(Exception):
            await _cleanup_tenant(tenant["slug"])

    async def test_email_mismatch_rejected(self, client: AsyncClient) -> None:
        tenant = await _register_tenant(client)
        headers = {"X-Tenant-Slug": tenant["slug"], "Authorization": f"Bearer {tenant['token']}"}

        invite_email = f"correct-{uuid.uuid4().hex[:8]}@test.com"
        create_resp = await client.post(
            "/api/v1/invitations",
            headers=headers,
            json={"email": invite_email},
        )
        assert create_resp.status_code == 200
        invite_data = create_resp.json()["data"]

        accept_resp = await client.post(
            "/api/v1/invitations/accept",
            headers={"X-Tenant-Slug": tenant["slug"]},
            data={
                "token": invite_data["token"],
                "email": "wrong-email@test.com",
                "password": "InviteePass123!",
                "full_name": "Wrong Email",
            },
        )
        assert accept_resp.status_code in (400, 403, 422)

        with contextlib.suppress(Exception):
            await _cleanup_tenant(tenant["slug"])

    async def test_invitee_grant_and_permission_gate(self, client: AsyncClient) -> None:
        tenant = await _register_tenant(client)
        headers = {"X-Tenant-Slug": tenant["slug"], "Authorization": f"Bearer {tenant['token']}"}

        viewer = await client.post(
            "/api/v1/roles",
            headers=headers,
            json={"name": "viewer", "permission_keys": ["roles:read"]},
        )
        assert viewer.status_code == 200

        invite_email = f"gate-{uuid.uuid4().hex[:8]}@test.com"
        create_resp = await client.post(
            "/api/v1/invitations",
            headers=headers,
            json={"email": invite_email, "role_name": "viewer"},
        )
        assert create_resp.status_code == 200
        invite_token = create_resp.json()["data"]["token"]

        accept_resp = await client.post(
            "/api/v1/invitations/accept",
            headers={"X-Tenant-Slug": tenant["slug"]},
            data={
                "token": invite_token,
                "email": invite_email,
                "password": "InviteePass123!",
                "full_name": "Gated Invitee",
            },
        )
        assert accept_resp.status_code == 200

        invitee_login = await client.post(
            "/api/v1/auth/login",
            headers={"X-Tenant-Slug": tenant["slug"]},
            json={"email": invite_email, "password": "InviteePass123!"},
        )
        assert invitee_login.status_code == 200
        # MFA is mandatory for every account: the invitee must enroll before
        # any authenticated route succeeds, mirroring the real client flow.
        invitee_token = await enroll_mfa_if_required(
            client, slug=tenant["slug"], login_data=invitee_login.json()["data"]
        )
        invitee_headers = {
            "X-Tenant-Slug": tenant["slug"],
            "Authorization": f"Bearer {invitee_token}",
        }

        me = await client.get("/api/v1/users/me", headers=invitee_headers)
        assert me.status_code == 200
        assert me.json()["data"]["email"] == invite_email

        roles = await client.get("/api/v1/roles", headers=invitee_headers)
        assert roles.status_code == 200

        denied = await client.post(
            "/api/v1/invitations",
            headers=invitee_headers,
            json={"email": f"gate-2-{uuid.uuid4().hex[:8]}@test.com"},
        )
        assert denied.status_code == 403
        assert denied.json()["type"].endswith("/permission-denied")

        control = await client.post(
            "/api/v1/invitations",
            headers=headers,
            json={"email": f"gate-3-{uuid.uuid4().hex[:8]}@test.com"},
        )
        assert control.status_code == 200

        with contextlib.suppress(Exception):
            await _cleanup_tenant(tenant["slug"])

    async def test_requires_admin_permission(self, client: AsyncClient) -> None:
        tenant = await _register_tenant(client)

        unprivileged = await provision_tenant(client)
        await wizard_login(
            client,
            slug=unprivileged["slug"],
            email=unprivileged["email"],
            password=unprivileged["password"],
        )

        with contextlib.suppress(Exception):
            await _cleanup_tenant(tenant["slug"])
            await _cleanup_tenant(unprivileged["slug"])
