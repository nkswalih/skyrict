from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pyotp
import pytest
from sqlalchemy import delete, select, update

from identity.db.session import async_session_factory
from identity.models.audit_log import AuditLogModel
from identity.models.session import SessionModel
from identity.models.tenant import TenantModel
from tests.integration.api.wizard import provision_tenant

if TYPE_CHECKING:
    from httpx import AsyncClient


_MFA_SECRETS: dict[str, str] = {}

_WIN11_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


async def _delete_tenant_by_slug(slug: str) -> None:
    async with async_session_factory() as session:
        await session.execute(delete(TenantModel).where(TenantModel.slug == slug))
        await session.commit()


async def _provision(client: AsyncClient) -> tuple[str, str]:
    tenant = await provision_tenant(client)
    return tenant["slug"], tenant["email"]


async def _enroll_mfa(client: AsyncClient, *, slug: str, access_token: str) -> str:
    headers = {"X-Tenant-Slug": slug, "Authorization": f"Bearer {access_token}"}
    setup = await client.post("/api/v1/mfa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["data"]["secret"]
    verify = await client.post(
        "/api/v1/mfa/verify", headers=headers, json={"code": pyotp.TOTP(secret).now()}
    )
    assert verify.status_code == 200
    return secret


async def _login(
    client: AsyncClient,
    *,
    slug: str,
    email: str,
    extra_headers: dict[str, str] | None = None,
) -> tuple[str, str, str]:
    headers = {"X-Tenant-Slug": slug}
    if extra_headers:
        headers.update(extra_headers)
    login = await client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={"email": email, "password": "TestPassword123!"},
    )
    assert login.status_code == 200
    data = login.json()["data"]
    user_id = str(data["user"]["id"])
    if data.get("mfa_required") and data["next_step"] == "mfa.verify":
        secret = _MFA_SECRETS[user_id]
        verify = await client.post(
            "/api/v1/auth/mfa/verify",
            headers={"X-Tenant-Slug": slug},
            json={"mfa_token": data["mfa_token"], "code": pyotp.TOTP(secret).now()},
        )
        assert verify.status_code == 200, verify.text
        redeemed = verify.json()["data"]
        return user_id, redeemed["access_token"], redeemed["refresh_token"]
    _MFA_SECRETS[user_id] = await _enroll_mfa(client, slug=slug, access_token=data["access_token"])
    return user_id, data["access_token"], data["refresh_token"]


async def _list_sessions(client: AsyncClient, *, slug: str, access_token: str) -> list[dict]:
    response = await client.get(
        "/api/v1/sessions",
        headers={"X-Tenant-Slug": slug, "Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]["sessions"]


async def _refresh(client: AsyncClient, *, slug: str, refresh_token: str):
    return await client.post(
        "/api/v1/auth/refresh",
        headers={"X-Tenant-Slug": slug},
        json={"refresh_token": refresh_token},
    )


@pytest.mark.integration
class TestSessionLifecycle:
    async def test_login_creates_session_listed_with_device_fields(
        self, client: AsyncClient
    ) -> None:
        slug, email = await _provision(client)
        user_id, access, _ = await _login(client, slug=slug, email=email)
        try:
            sessions = await _list_sessions(client, slug=slug, access_token=access)

            assert len(sessions) == 1
            session = sessions[0]
            assert session["user_id"] == user_id
            assert session["status"] == "active"
            assert session["last_active_at"]
            assert session["user_agent"]  # httpx sends python-httpx/<version>
            assert session["device_type"] == "service"
            assert session["browser_name"] is None
            assert session["os_name"] is None
            assert session["device_family"] == "Python HTTPX"
            assert session["device_model"] is None
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_old_refresh_token_reuse_kills_the_session_chain(
        self, client: AsyncClient
    ) -> None:
        slug, email = await _provision(client)
        user_id, access, refresh = await _login(client, slug=slug, email=email)
        try:
            first = await _refresh(client, slug=slug, refresh_token=refresh)
            assert first.status_code == 200
            assert first.json()["data"]["refresh_token"] != refresh

            # Age the tolerance window past expiry: a genuine re-transmission of
            # the rotated-out token must STILL chain-kill the family. The
            # within-grace tolerance is covered by the test below.
            async with async_session_factory() as session:
                await session.execute(
                    update(SessionModel)
                    .where(SessionModel.user_id == uuid.UUID(user_id))
                    .values(previous_token_valid_until=datetime.now(UTC) - timedelta(seconds=1))
                )
                await session.commit()

            reuse = await _refresh(client, slug=slug, refresh_token=refresh)
            assert reuse.status_code == 401
            assert reuse.json()["type"].endswith("/token-reuse-detected")

            assert await _list_sessions(client, slug=slug, access_token=access) == []

            async with async_session_factory() as session:
                row = await session.scalar(
                    select(AuditLogModel).where(
                        AuditLogModel.action == "auth.refresh.reuse_detected",
                        AuditLogModel.actor_user_id == uuid.UUID(user_id),
                    )
                )
                assert row is not None
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_refresh_reuse_within_grace_is_tolerated(self, client: AsyncClient) -> None:
        slug, email = await _provision(client)
        _, access, refresh = await _login(client, slug=slug, email=email)
        try:
            first = await _refresh(client, slug=slug, refresh_token=refresh)
            assert first.status_code == 200
            assert first.json()["data"]["refresh_token"] != refresh

            # Benign race (two tabs / a dropped response): presenting the token
            # that was rotated out milliseconds ago issues a fresh pair instead
            # of revoking the whole session family.
            tolerated = await _refresh(client, slug=slug, refresh_token=refresh)
            assert tolerated.status_code == 200
            assert tolerated.json()["data"]["refresh_token"] != refresh

            sessions = await _list_sessions(client, slug=slug, access_token=access)
            assert len(sessions) == 1
            assert sessions[0]["status"] == "active"
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_repeated_within_grace_replays_do_not_escalate_to_reuse(
        self, client: AsyncClient
    ) -> None:
        """A K-way benign race must not walk the replayed token out of the window.

        The reuse grace window remembers exactly one previous refresh token.
        Rotating *inside* the window and storing the token that was just
        consumed used to overwrite that memory, so each concurrent replay of
        the same cookie pushed the original token one generation further from
        the session record. The third replay was then classified as theft and
        revoked the whole family - taking down a browser and a test client
        that shared one cookie jar, for a race that is not an attack.

        The fix carries the protected token forward and extends its deadline
        instead, so any number of replays stay inside a single rotation.
        """
        slug, email = await _provision(client)
        user_id, access, refresh = await _login(client, slug=slug, email=email)
        try:
            first = await _refresh(client, slug=slug, refresh_token=refresh)
            assert first.status_code == 200

            # Replay the same (already rotated-out) token repeatedly. Each is a
            # benign race: a second tab, a dropped response, the page hydrating
            # while the test client hydrates the same cookie.
            for attempt in range(4):
                tolerated = await _refresh(client, slug=slug, refresh_token=refresh)
                assert tolerated.status_code == 200, f"replay {attempt} was rejected"
                assert tolerated.json()["data"]["refresh_token"] != refresh

            sessions = await _list_sessions(client, slug=slug, access_token=access)
            assert len(sessions) == 1
            assert sessions[0]["status"] == "active"

            # The chain-kill is specifically what must NOT have happened.
            async with async_session_factory() as session:
                reuse_audit = await session.scalar(
                    select(AuditLogModel).where(
                        AuditLogModel.action == "auth.refresh.reuse_detected",
                        AuditLogModel.actor_user_id == uuid.UUID(user_id),
                    )
                )
                assert reuse_audit is None
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_reuse_after_grace_window_still_kills_the_chain(
        self, client: AsyncClient
    ) -> None:
        """The widened window must not disarm theft detection.

        The sticky grace token survives any number of replays, so a token
        replayed long after the window has to be rejected on the deadline -
        otherwise "carry the token forward" would quietly turn into
        "accept this token forever".
        """
        slug, email = await _provision(client)
        user_id, access, refresh = await _login(client, slug=slug, email=email)
        try:
            first = await _refresh(client, slug=slug, refresh_token=refresh)
            assert first.status_code == 200

            # One benign replay first, so the window is genuinely sticky and
            # the only thing that can reject the next attempt is the deadline.
            tolerated = await _refresh(client, slug=slug, refresh_token=refresh)
            assert tolerated.status_code == 200

            async with async_session_factory() as session:
                await session.execute(
                    update(SessionModel)
                    .where(SessionModel.user_id == uuid.UUID(user_id))
                    .values(previous_token_valid_until=datetime.now(UTC) - timedelta(seconds=1))
                )
                await session.commit()

            reuse = await _refresh(client, slug=slug, refresh_token=refresh)
            assert reuse.status_code == 401
            assert reuse.json()["type"].endswith("/token-reuse-detected")
            assert await _list_sessions(client, slug=slug, access_token=access) == []
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_logout_revokes_only_the_matching_session(self, client: AsyncClient) -> None:
        slug, email = await _provision(client)
        _, access_a, refresh_a = await _login(client, slug=slug, email=email)
        _, access_b, _ = await _login(client, slug=slug, email=email)
        try:
            assert len(await _list_sessions(client, slug=slug, access_token=access_a)) == 2

            logout = await client.post(
                "/api/v1/auth/logout",
                headers={
                    "X-Tenant-Slug": slug,
                    "Authorization": f"Bearer {access_a}",
                },
                json={"refresh_token": refresh_a},
            )
            assert logout.status_code == 200

            sessions = await _list_sessions(client, slug=slug, access_token=access_b)
            assert len(sessions) == 1

            reuse = await _refresh(client, slug=slug, refresh_token=refresh_a)
            assert reuse.status_code == 401
            assert reuse.json()["type"].endswith("/token-reuse-detected")
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_revoke_session_by_id_and_foreign_id_404(self, client: AsyncClient) -> None:
        slug, email = await _provision(client)
        _, access_a, _ = await _login(client, slug=slug, email=email)
        _, access_b, _ = await _login(client, slug=slug, email=email)
        try:
            sessions = await _list_sessions(client, slug=slug, access_token=access_a)
            assert len(sessions) == 2
            victim_id = sessions[0]["id"]

            foreign = await client.delete(
                f"/api/v1/sessions/{uuid.uuid4()}",
                headers={"X-Tenant-Slug": slug, "Authorization": f"Bearer {access_a}"},
            )
            assert foreign.status_code == 404

            revoke = await client.delete(
                f"/api/v1/sessions/{victim_id}",
                headers={"X-Tenant-Slug": slug, "Authorization": f"Bearer {access_a}"},
            )
            assert revoke.status_code == 200

            remaining = await _list_sessions(client, slug=slug, access_token=access_b)
            assert len(remaining) == 1
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_login_captures_structured_device_fields(self, client: AsyncClient) -> None:
        slug, email = await _provision(client)
        _, access, _ = await _login(
            client,
            slug=slug,
            email=email,
            extra_headers={
                "User-Agent": _WIN11_UA,
                "Sec-CH-UA": '"Chromium";v="151", "Google Chrome";v="151"',
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-CH-UA-Platform-Version": '"15.0.0"',
                "Sec-CH-UA-Mobile": "?0",
            },
        )
        try:
            sessions = await _list_sessions(client, slug=slug, access_token=access)
            assert len(sessions) == 1
            session = sessions[0]

            assert session["user_agent"] == _WIN11_UA
            assert session["device_type"] == "desktop"
            assert session["browser_name"] == "Chrome"
            assert session["browser_version"] == "151"
            assert session["os_name"] == "Windows"
            assert session["os_version"] == "11"
            assert session["device_family"] == "Windows PC"
            assert session["device_model"] is None
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_programmatic_client_login_is_a_service(self, client: AsyncClient) -> None:
        slug, email = await _provision(client)
        _, access, _ = await _login(
            client,
            slug=slug,
            email=email,
            extra_headers={"User-Agent": "node"},
        )
        try:
            sessions = await _list_sessions(client, slug=slug, access_token=access)
            assert len(sessions) == 1
            session = sessions[0]

            assert session["device_type"] == "service"
            assert session["device_family"] == "Node.js"
            assert session["browser_name"] is None
            assert session["os_name"] is None
            assert session["device"] == "Node.js"
        finally:
            await _delete_tenant_by_slug(slug)

    async def test_spoofed_forwarded_header_is_ignored(self, client: AsyncClient) -> None:
        slug, email = await _provision(client)
        _, access, _ = await _login(
            client,
            slug=slug,
            email=email,
            extra_headers={"X-Forwarded-For": "8.8.8.8, 6.6.6.6"},
        )
        try:
            sessions = await _list_sessions(client, slug=slug, access_token=access)
            assert len(sessions) == 1
            session = sessions[0]

            assert session["ip_address"] != "8.8.8.8"
            assert session["ip_address"] != "6.6.6.6"
        finally:
            await _delete_tenant_by_slug(slug)
