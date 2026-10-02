"""Unit tests for the auth feature AuthenticationService (fake ports)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from identity.core.config import Environment, settings
from identity.core.constants import (
    LOGIN_FAILED_MESSAGE,
    RESERVED_EMAILS,
    RESERVED_SLUGS,
    SYSTEM_ROLE_DEFINITIONS,
)
from identity.core.security import (
    create_refresh_token,
    hash_password,
    hash_refresh_token,
)
from identity.core.tenant_context import TenantContext
from identity.domain.entities import (
    Membership,
    MembershipStatus,
    Role,
    Session,
    SessionStatus,
    Tenant,
    User,
)
from identity.domain.value_objects import TokenPair
from identity.features.auth.schemas import (
    BillingAddress,
    CreateOrganizationRequest,
    LoginRequest,
)
from identity.features.auth.service import AuthenticationService, TokenService
from identity.features.auth.verification_store import SignupFlow
from skyrict_common.exceptions import (
    AuthenticationError,
    ConflictError,
    TokenInvalidError,
    TokenReuseDetectedError,
    UserAlreadyExistsError,
    UserNotFoundError,
    ValidationError,
)

if TYPE_CHECKING:
    from identity.core.email_templates import SecurityAlert


class FakeUserRepo:
    """In-memory UserRepositoryPort double (subset used by auth flows)."""

    def __init__(self, users: list[User] | None = None) -> None:
        self.users: dict[uuid.UUID, User] = {}
        for user in users or []:
            if user.id is None:
                user.id = uuid.uuid4()
            self.users[user.id] = user
        self.created: list[User] = []

    async def get_by_id(self, user_id: str | uuid.UUID) -> User | None:
        return self.users.get(uuid.UUID(str(user_id)))

    async def get_by_email(self, tenant_id: str | uuid.UUID, email: str) -> User | None:
        for user in self.users.values():
            if user.email == email and str(user.tenant_id) == str(tenant_id):
                return user
        return None

    async def email_exists(self, tenant_id: str | uuid.UUID, email: str) -> bool:
        return await self.get_by_email(tenant_id, email) is not None

    async def email_exists_global(self, email: str) -> bool:
        return any(user.email == email for user in self.users.values())

    async def create(self, user: User) -> User:
        if user.id is None:
            user.id = uuid.uuid4()
        self.users[user.id] = user
        self.created.append(user)
        return user

    async def update_profile(
        self,
        user_id: str | uuid.UUID,
        *,
        full_name: str | None = None,
        email: str | None = None,
    ) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        if full_name is not None:
            user.full_name = full_name
        if email is not None:
            user.email = email
        return user

    async def update_password_hash(self, user_id: str | uuid.UUID, password_hash: str) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        user.password_hash = password_hash
        return user

    async def mark_verified(self, user_id: str | uuid.UUID) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        user.is_verified = True
        return user


class FakeTenantRepo:
    """In-memory TenantRepositoryPort double."""

    def __init__(self, tenants: list[Tenant] | None = None) -> None:
        self.tenants: dict[uuid.UUID, Tenant] = {}
        for tenant in tenants or []:
            if tenant.id is None:
                tenant.id = uuid.uuid4()
            self.tenants[tenant.id] = tenant
        self.created: list[Tenant] = []

    async def get_by_id(self, tenant_id: str | uuid.UUID) -> Tenant | None:
        return self.tenants.get(uuid.UUID(str(tenant_id)))

    async def get_by_slug(self, slug: str) -> Tenant | None:
        for tenant in self.tenants.values():
            if tenant.slug == slug:
                return tenant
        return None

    async def slug_exists(self, slug: str) -> bool:
        return await self.get_by_slug(slug) is not None

    async def create(self, tenant: Tenant) -> Tenant:
        if tenant.id is None:
            tenant.id = uuid.uuid4()
        self.tenants[tenant.id] = tenant
        self.created.append(tenant)
        return tenant


class FakeRoleRepo:
    """In-memory RoleRepositoryPort double."""

    def __init__(self, roles_for_user: dict[uuid.UUID, list[str]] | None = None) -> None:
        self.roles_by_user: dict[uuid.UUID, list[str]] = dict(roles_for_user or {})
        self.created: list[Role] = []
        self.grants: list[tuple[str, str, str, str]] = []

    async def create(self, role: Role) -> Role:
        if role.id is None:
            role.id = uuid.uuid4()
        self.created.append(role)
        return role

    async def get_by_id(self, role_id: str | uuid.UUID) -> Role | None:
        for role in self.created:
            if role.id is not None and str(role.id) == str(role_id):
                return role
        return None

    async def get_by_name(self, tenant_id: str | uuid.UUID, name: str) -> Role | None:
        for role in self.created:
            if role.name == name and str(role.tenant_id) == str(tenant_id):
                return role
        return None

    async def list_by_tenant(
        self, tenant_id: str | uuid.UUID, *, offset: int = 0, limit: int = 20
    ) -> list[Role]:
        roles = [role for role in self.created if str(role.tenant_id) == str(tenant_id)]
        return roles[offset : offset + limit]

    async def grant_to_user(
        self,
        *,
        user_id: str | uuid.UUID,
        role_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
        scope_id: str | uuid.UUID,
        scope_type=...,
    ) -> None:
        self.grants.append((str(user_id), str(role_id), str(tenant_id), str(scope_id)))

    async def get_roles_for_user(
        self, user_id: str | uuid.UUID, tenant_id: str | uuid.UUID
    ) -> list[str]:
        return self.roles_by_user.get(uuid.UUID(str(user_id)), [])


class FakeTokenService:
    """TokenService double - returns a fixed TokenPair, records call args."""

    def __init__(self) -> None:
        self.pairs_created: list[tuple[str, str, str | None]] = []

    async def create_token_pair(
        self, *, user_id: str, tenant_id: str, session_id: str | None = None
    ) -> TokenPair:
        self.pairs_created.append((user_id, tenant_id, session_id))
        return TokenPair(access_token="access-token", refresh_token="refresh-token")


class FakeAuditService:
    """AuditService double - records log() calls."""

    def __init__(self) -> None:
        self.events: list[dict[str, str | None]] = []

    async def log(
        self,
        *,
        action: str,
        target: str,
        user_id: str | None = None,
        details: dict[str, object] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        self.events.append(
            {"action": action, "target": target, "user_id": user_id, "tenant_id": tenant_id}
        )


class FakeEmailService:
    """EmailService double - records send_verification calls."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str | None]] = []

    async def send_verification(
        self, *, to: str, full_name: str, token: str, base_url: str | None = None
    ) -> None:
        self.sent.append({"to": to, "full_name": full_name, "token": token, "base_url": base_url})

    async def send_otp(self, *, to: str, code: str) -> None:
        self.sent.append({"to": to, "code": code})

    async def send_security_alert(self, *, alert: SecurityAlert) -> None:
        self.sent.append(
            {
                "to": alert.to,
                "full_name": alert.full_name,
                "event_type": alert.event_type,
                "ip_address": alert.ip_address,
                "location": alert.location,
                "browser": alert.browser,
                "os": alert.os,
                "device": alert.device,
                "auth_method": alert.auth_method,
                "session_id_masked": alert.session_id_masked,
                "date_time": alert.date_time,
                "review_url": alert.review_url,
                "secure_url": alert.secure_url,
            }
        )


class FakeSessionService:
    def __init__(self, prior_device: bool = True) -> None:
        self.prior_device = prior_device
        self.created: list[Session] = []
        self.prior_device_checks: list[tuple[uuid.UUID, str | None, str | None]] = []

    async def has_prior_device(
        self,
        user_id: str | uuid.UUID,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> bool:
        self.prior_device_checks.append((uuid.UUID(str(user_id)), user_agent, ip_address))
        return self.prior_device

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        refresh_token_hash: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
        device_info: dict[str, object] | None = None,
        location: str | None = None,
        session_id: uuid.UUID | None = None,
    ) -> Session:
        session = Session(
            id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            refresh_token_hash=refresh_token_hash,
            user_agent=user_agent,
            ip_address=ip_address,
            device_info=device_info,
            location=location,
        )
        self.created.append(session)
        return session

    # -- refresh-rotation surface (mirrors SessionService) --------------------
    # `create_session` above only covers the login path; the refresh path also
    # needs lookup, in-place rotation, and the revoke/expire side effects that
    # reuse detection triggers.

    def store(self, session: Session) -> Session:
        self.created.append(session)
        return session

    async def get_session(
        self,
        session_id: str | uuid.UUID,
        *,
        tenant_id: str | uuid.UUID | None = None,
    ) -> Session | None:
        for session in self.created:
            if session.id != uuid.UUID(str(session_id)):
                continue
            if tenant_id is not None and session.tenant_id != uuid.UUID(str(tenant_id)):
                return None
            return session
        return None

    async def rotate_session(
        self,
        session_id: str | uuid.UUID,
        *,
        refresh_token_hash: str,
        expires_at: datetime,
        tenant_id: str | uuid.UUID | None = None,
        previous_refresh_token_hash: str | None = None,
        previous_token_valid_until: datetime | None = None,
    ) -> Session | None:
        session = await self.get_session(session_id, tenant_id=tenant_id)
        if session is None:
            return None
        if session.status is not SessionStatus.ACTIVE:
            return None
        session.refresh_token_hash = refresh_token_hash
        session.previous_refresh_token_hash = previous_refresh_token_hash
        session.previous_token_valid_until = previous_token_valid_until
        session.expires_at = expires_at
        return session

    async def expire_session(
        self,
        session_id: str | uuid.UUID,
        *,
        tenant_id: str | uuid.UUID | None = None,
    ) -> Session | None:
        session = await self.get_session(session_id, tenant_id=tenant_id)
        if session is None:
            return None
        if session.status is SessionStatus.ACTIVE:
            session.status = SessionStatus.EXPIRED
            session.expired_at = datetime.now(UTC)
        return session

    async def revoke_family(
        self,
        family_id: str | uuid.UUID,
        *,
        tenant_id: str | uuid.UUID | None = None,
    ) -> None:
        for session in self.created:
            if session.token_family_id != uuid.UUID(str(family_id)):
                continue
            if tenant_id is not None and session.tenant_id != uuid.UUID(str(tenant_id)):
                continue
            if session.status is SessionStatus.ACTIVE:
                session.status = SessionStatus.REVOKED
                session.revoked_at = datetime.now(UTC)

    async def revoke_all_sessions(
        self, user_id: str | uuid.UUID, tenant_id: str | uuid.UUID | None = None
    ) -> None:
        for session in self.created:
            if session.user_id != uuid.UUID(str(user_id)):
                continue
            if tenant_id is not None and session.tenant_id != uuid.UUID(str(tenant_id)):
                continue
            if session.status is SessionStatus.ACTIVE:
                session.status = SessionStatus.REVOKED
                session.revoked_at = datetime.now(UTC)

    async def commit(self) -> None:
        """No-op: the double mutates entities in place, there is no unit of work."""


class FakeMembershipService:
    def __init__(self) -> None:
        self.active: list[Membership] = []

    async def create_active(
        self,
        *,
        tenant_id: str | uuid.UUID,
        user_id: str | uuid.UUID,
        role_id: str | uuid.UUID | None = None,
        invited_email: str | None = None,
    ) -> Membership:
        membership = Membership(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(str(tenant_id)),
            user_id=uuid.UUID(str(user_id)),
            invited_email=invited_email.strip().lower() if invited_email else None,
            role_id=uuid.UUID(str(role_id)) if role_id is not None else None,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime.now(UTC),
        )
        self.active.append(membership)
        return membership


class FakeChallengeStore:
    def __init__(self) -> None:
        self.challenges: dict[str, dict[str, str]] = {}
        self.consumed: list[str] = []
        self.attempts: dict[str, int] = {}

    async def create(self, *, user_id: str, tenant_id: str) -> str:
        token = f"mfa-token-{len(self.challenges) + 1}"
        self.challenges[token] = {"user_id": user_id, "tenant_id": tenant_id}
        self.attempts[token] = 0
        return token

    async def get(self, token: str) -> dict[str, str] | None:
        if token in self.consumed:
            return None
        return self.challenges.get(token)

    async def get_attempts(self, token: str) -> int:
        return self.attempts.get(token, 0)

    async def increment_attempts(self, token: str) -> int:
        count = self.attempts.get(token, 0) + 1
        self.attempts[token] = count
        return count

    async def consume(self, token: str) -> None:
        self.consumed.append(token)
        self.challenges.pop(token, None)
        self.attempts.pop(token, None)


class FakeVerificationStore:
    """In-memory VerificationStore double keyed by email/token."""

    def __init__(self) -> None:
        self.otp_hashes: dict[str, str] = {}
        self.attempts: dict[str, int] = {}
        self.resend_until: dict[str, float] = {}
        self.tokens: dict[str, dict[str, str]] = {}
        self.flows: dict[str, SignupFlow] = {}
        self.flow_sends: dict[str, int] = {}
        self.now: float = 0.0

    async def set_otp(self, email: str, otp_hash: str) -> None:
        self.otp_hashes[email.lower()] = otp_hash
        self.attempts[email.lower()] = 0

    async def get_otp_hash(self, email: str) -> str | None:
        return self.otp_hashes.get(email.lower())

    async def delete_otp(self, email: str) -> None:
        self.otp_hashes.pop(email.lower(), None)
        self.attempts.pop(email.lower(), None)

    async def get_attempts(self, email: str) -> int:
        return self.attempts.get(email.lower(), 0)

    async def increment_attempts(self, email: str) -> int:
        count = self.attempts.get(email.lower(), 0) + 1
        self.attempts[email.lower()] = count
        return count

    async def is_resend_blocked(self, email: str) -> bool:
        return self.resend_until.get(email.lower(), 0.0) > self.now

    async def mark_resend(self, email: str) -> None:
        self.resend_until[email.lower()] = self.now + settings.OTP_RESEND_COOLDOWN_SECONDS

    async def resend_in(self, email: str) -> int:
        remaining = self.resend_until.get(email.lower(), 0.0) - self.now
        return max(int(remaining), 0)

    async def set_signup_flow(self, token: str, email: str) -> None:
        self.flows[token] = SignupFlow(email=email, sends=0)
        self.flow_sends[token] = 0

    async def get_signup_flow(self, token: str) -> SignupFlow | None:
        flow = self.flows.get(token)
        if flow is None:
            return None
        return SignupFlow(email=flow.email, sends=self.flow_sends.get(token, 0))

    async def consume_signup_flow_send(self, token: str) -> int:
        self.flow_sends[token] = self.flow_sends.get(token, 0) + 1
        return self.flow_sends[token]

    async def set_verification_token(self, token: str, email: str, password_hash: str) -> str:
        self.tokens[token] = {"email": email, "password_hash": password_hash}
        return token

    async def get_verification_token(self, token: str) -> dict[str, str] | None:
        payload = self.tokens.get(token)
        if payload is None:
            return None
        return dict(payload)

    async def update_verification_token_password(self, token: str, password_hash: str) -> None:
        payload = self.tokens.get(token)
        if payload is not None:
            self.tokens[token] = {"email": payload["email"], "password_hash": password_hash}

    async def delete_verification_token(self, token: str) -> None:
        self.tokens.pop(token, None)


class FakeTurnstile:
    """Turnstile double with a scripted verdict."""

    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[str | None] = []

    async def verify(self, token: str | None) -> bool:
        self.calls.append(token)
        return self.result


class FakeCaptchaStore:
    """CAPTCHA double that accepts every answer unless scripted otherwise."""

    def __init__(self, valid: bool = True) -> None:
        self.valid = valid
        self.issued: list[str] = []
        self.verifications: list[tuple[str, str]] = []

    async def issue(self, answer: str) -> str:
        self.issued.append(answer)
        return f"captcha-{len(self.issued)}"

    async def verify(self, captcha_id: str, answer: str) -> bool:
        self.verifications.append((captcha_id, answer))
        return self.valid


class _Harness:
    """Wires AuthenticationService against in-memory port doubles."""

    def __init__(
        self,
        *,
        users: list[User] | None = None,
        tenants: list[Tenant] | None = None,
        roles_for_user: dict[uuid.UUID, list[str]] | None = None,
        prior_device: bool = True,
        verification_store: FakeVerificationStore | None = None,
        turnstile: FakeTurnstile | None = None,
        captcha_store: FakeCaptchaStore | None = None,
    ) -> None:
        self.user_repo = FakeUserRepo(users)
        self.tenant_repo = FakeTenantRepo(tenants)
        self.role_repo = FakeRoleRepo(roles_for_user)
        self.token_svc = FakeTokenService()
        self.audit_svc = FakeAuditService()
        self.email_svc = FakeEmailService()
        self.session_svc = FakeSessionService(prior_device=prior_device)
        self.membership_svc = FakeMembershipService()
        self.verification_store = verification_store or FakeVerificationStore()
        self.turnstile = turnstile or FakeTurnstile()
        self.captcha_store = captcha_store or FakeCaptchaStore()
        self.challenge_store = FakeChallengeStore()
        self.service = AuthenticationService(
            self.user_repo,
            self.tenant_repo,
            self.role_repo,
            self.token_svc,
            self.audit_svc,
            self.email_svc,
            self.session_svc,
            self.membership_svc,
            self.verification_store,
            self.turnstile,
            mfa_challenge_store=self.challenge_store,
            captcha_store=self.captcha_store,
        )


@pytest.fixture
def tenant_ctx() -> str:
    tenant_id = str(uuid.uuid4())
    TenantContext.set(tenant_id)
    yield tenant_id
    TenantContext.reset()


def _make_user(
    *,
    tenant_id: uuid.UUID | None = None,
    email: str = "user@example.com",
    password: str = "Password1!",
    is_active: bool = True,
    is_verified: bool = True,
    mfa_enabled: bool = False,
) -> User:
    return User(
        tenant_id=tenant_id if tenant_id is not None else uuid.UUID(TenantContext.get()),
        email=email,
        password_hash=hash_password(password),
        full_name="Test User",
        is_active=is_active,
        is_verified=is_verified,
        mfa_enabled=mfa_enabled,
        id=uuid.uuid4(),
    )


class TestRefreshTokenRotation:
    """Refresh-token rotation and the reuse grace window.

    The grace window exists so a benign race (two tabs, a dropped response, a
    page hydrating while a test client hydrates the same cookie) does not get
    answered by a token-family chain-kill. These are unit-level tests because
    the behaviour under test is pure service logic over the session record -
    they run in the no-database lane, so a regression is caught without a
    provisioned Postgres.
    """

    def _seed(self, tenant_ctx: str) -> tuple[TokenService, FakeSessionService, Session, str]:
        user = _make_user()
        harness = _Harness(users=[user])
        session = harness.session_svc.store(
            Session(
                id=uuid.uuid4(),
                user_id=user.id,
                tenant_id=uuid.UUID(tenant_ctx),
                refresh_token_hash="",
                token_family_id=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
        refresh = create_refresh_token(
            str(user.id), tenant_id=tenant_ctx, session_id=str(session.id)
        )
        session.refresh_token_hash = hash_refresh_token(refresh)
        tokens = TokenService(harness.session_svc, harness.audit_svc)
        return tokens, harness, session, refresh

    async def test_repeated_within_grace_replays_do_not_escalate_to_reuse(
        self, tenant_ctx: str
    ) -> None:
        """A K-way race must not walk the replayed token out of the window.

        The window remembers exactly one previous refresh token. Rotating
        *inside* the window and storing the token that was just consumed
        overwrote that memory, so every concurrent replay of the same cookie
        pushed the original token one generation further from the record. The
        third replay was then classified as theft and revoked the family - for
        a race that is not an attack.
        """
        tokens, harness, session, refresh = self._seed(tenant_ctx)
        protected_hash = hash_refresh_token(refresh)

        first = await tokens.refresh_tokens(refresh)
        assert session.previous_refresh_token_hash == protected_hash
        assert session.previous_token_valid_until is not None
        # The deadline is set once, when the protected token was retired.
        deadline = session.previous_token_valid_until

        for attempt in range(4):
            tolerated = await tokens.refresh_tokens(refresh)
            assert tolerated.refresh_token != first.refresh_token, attempt
            # The protected token is still the one the window is guarding...
            assert session.previous_refresh_token_hash == protected_hash
            assert session.status is SessionStatus.ACTIVE
            # ...and tolerating a replay must NOT push the deadline out. A
            # window a caller can extend by replaying is not a window: a
            # captured token would stay replayable for as long as its holder
            # kept presenting it, which is the persistence this control exists
            # to bound.
            assert session.previous_token_valid_until == deadline, attempt

        # The chain-kill is specifically what must not have happened.
        assert not [
            event
            for event in harness.audit_svc.events
            if event["action"] == "auth.refresh.reuse_detected"
        ]

    async def test_reuse_past_the_grace_window_still_kills_the_family(
        self, tenant_ctx: str
    ) -> None:
        """Carrying the token forward must not become accepting it forever.

        The sticky token survives any number of replays, so a token replayed
        after the deadline has to be rejected on the deadline - otherwise the
        theft detection this window is built around would be silently off.
        """
        tokens, _harness, session, refresh = self._seed(tenant_ctx)

        await tokens.refresh_tokens(refresh)
        await tokens.refresh_tokens(refresh)
        assert session.status is SessionStatus.ACTIVE

        # Age the window past its deadline, as the wall clock would.
        assert session.previous_token_valid_until is not None
        session.previous_token_valid_until = datetime.now(UTC) - timedelta(seconds=1)

        with pytest.raises(TokenReuseDetectedError):
            await tokens.refresh_tokens(refresh)

        assert session.status is SessionStatus.REVOKED

    async def test_a_token_two_generations_old_is_reuse(self, tenant_ctx: str) -> None:
        """The grace window protects one token, not a whole lineage.

        Rotating twice with the *current* token retires the original for good:
        a replay of it is then outside the remembered token, not merely late.
        """
        tokens, _harness, session, refresh = self._seed(tenant_ctx)

        original = refresh
        first = await tokens.refresh_tokens(original)
        await tokens.refresh_tokens(first.refresh_token)

        # The window now guards `first`'s token, not the original.
        assert session.previous_refresh_token_hash == hash_refresh_token(first.refresh_token)

        with pytest.raises(TokenReuseDetectedError):
            await tokens.refresh_tokens(original)

        assert session.status is SessionStatus.REVOKED


class TestLogin:
    async def test_success_returns_tokens_and_user(self, tenant_ctx: str) -> None:
        user = _make_user()
        harness = _Harness(users=[user])

        result = await harness.service.login(LoginRequest(email=user.email, password="Password1!"))

        assert result["access_token"] == "access-token"
        assert result["refresh_token"] == "refresh-token"
        assert result["token_type"] == "Bearer"
        assert result["mfa_required"] is True
        assert result["next_step"] == "mfa.setup"
        assert result["user"] is user
        user_id, created_tenant, session_id = harness.token_svc.pairs_created[0]
        assert (user_id, created_tenant) == (str(user.id), tenant_ctx)
        assert session_id is not None
        assert harness.session_svc.prior_device_checks == [(user.id, None, None)]
        assert [s.id for s in harness.session_svc.created] == [uuid.UUID(session_id)]
        assert harness.session_svc.created[0].user_id == user.id
        assert harness.session_svc.created[0].tenant_id == uuid.UUID(tenant_ctx)
        assert harness.audit_svc.events == [
            {
                "action": "auth.login.success",
                "target": f"user:{user.id}",
                "user_id": str(user.id),
                "tenant_id": None,
            }
        ]
        assert harness.email_svc.sent == []

    async def test_new_device_sends_security_alert(self, tenant_ctx: str) -> None:
        user = _make_user()
        harness = _Harness(users=[user], prior_device=False)

        await harness.service.login(
            LoginRequest(email=user.email, password="Password1!"),
            ip_address="203.0.113.7",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )

        assert len(harness.email_svc.sent) == 1
        alert = harness.email_svc.sent[0]
        assert alert["to"] == user.email
        assert alert["full_name"] == "Test User"
        assert alert["event_type"] == "new_device"
        assert alert["ip_address"] == "203.0.113.***"
        assert alert["auth_method"] == "Password"
        assert alert["browser"].startswith("Chrome")
        assert alert["os"].startswith("Windows")
        assert alert["session_id_masked"].endswith("••••")
        assert len(alert["session_id_masked"]) == 12
        assert alert["date_time"]
        assert alert["review_url"] is None
        assert alert["secure_url"] is None

    async def test_new_device_alert_urls_are_tenant_scoped(
        self, tenant_ctx: str, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "ENVIRONMENT", Environment.DEV)
        monkeypatch.setattr(settings, "SECURITY_CONSOLE_BASE_URL", "")
        monkeypatch.setattr(settings, "SECURITY_CONSOLE_DEV_PORT", 3000)
        monkeypatch.setattr(settings, "BASE_DOMAIN", "")
        tenant_id = uuid.UUID(tenant_ctx)
        user = _make_user(tenant_id=tenant_id)
        tenant = Tenant(id=tenant_id, name="Acme Corp", slug="acme")
        harness = _Harness(users=[user], tenants=[tenant], prior_device=False)

        await harness.service.login(
            LoginRequest(email=user.email, password="Password1!"),
            ip_address="203.0.113.7",
            user_agent="",
        )

        assert len(harness.email_svc.sent) == 1
        alert = harness.email_svc.sent[0]
        assert alert["review_url"] == "http://acme.localhost:3000/settings/security"
        assert alert["secure_url"] == "http://acme.localhost:3000/settings/security/password"

    async def test_new_device_alert_masks_ip_and_unknowns(self, tenant_ctx: str) -> None:
        user = _make_user()
        harness = _Harness(users=[user], prior_device=False)

        await harness.service.login(
            LoginRequest(email=user.email, password="Password1!"),
            ip_address=None,
            user_agent="",
        )

        assert len(harness.email_svc.sent) == 1
        alert = harness.email_svc.sent[0]
        assert alert["ip_address"] == "Unknown"
        assert alert["location"] == "Unknown"
        assert alert["browser"] == "Unknown"
        assert alert["os"] == "Unknown"

    async def test_unverified_user_raises(self, tenant_ctx: str) -> None:
        user = _make_user(is_verified=False)
        harness = _Harness(users=[user])

        with pytest.raises(AuthenticationError):
            await harness.service.login(LoginRequest(email=user.email, password="Password1!"))

        assert harness.token_svc.pairs_created == []
        assert harness.audit_svc.events == [
            {
                "action": "auth.login.failed",
                "target": f"user:{user.id}",
                "user_id": str(user.id),
                "tenant_id": tenant_ctx,
            }
        ]

    async def test_tenant_owner_without_mfa_requires_mfa(self, tenant_ctx: str) -> None:
        user = _make_user()
        harness = _Harness(users=[user], roles_for_user={user.id: ["tenant_owner"]})

        result = await harness.service.login(LoginRequest(email=user.email, password="Password1!"))

        assert result["mfa_required"] is True
        assert result["next_step"] == "mfa.setup"

    async def test_enrolled_owner_gets_challenge_not_tokens(self, tenant_ctx: str) -> None:
        user = _make_user(mfa_enabled=True)
        harness = _Harness(users=[user], roles_for_user={user.id: ["tenant_owner"]})

        result = await harness.service.login(LoginRequest(email=user.email, password="Password1!"))

        assert result["mfa_required"] is True
        assert result["next_step"] == "mfa.verify"
        assert result["mfa_token"] == "mfa-token-1"
        assert result["access_token"] is None
        assert result["refresh_token"] is None
        assert harness.token_svc.pairs_created == []
        assert harness.audit_svc.events == [
            {
                "action": "auth.login.mfa_challenged",
                "target": f"user:{user.id}",
                "user_id": str(user.id),
                "tenant_id": None,
            }
        ]

    async def test_member_without_mfa_requires_mfa(self, tenant_ctx: str) -> None:
        user = _make_user()
        harness = _Harness(users=[user])

        result = await harness.service.login(LoginRequest(email=user.email, password="Password1!"))

        assert result["mfa_required"] is True
        assert result["next_step"] == "mfa.setup"

    async def test_unknown_email_raises(self, tenant_ctx: str) -> None:
        harness = _Harness()

        with pytest.raises(AuthenticationError) as excinfo:
            await harness.service.login(
                LoginRequest(email="nobody@example.com", password="Password1!")
            )

        assert excinfo.value.message == LOGIN_FAILED_MESSAGE
        assert harness.token_svc.pairs_created == []
        assert harness.audit_svc.events == [
            {
                "action": "auth.login.failed",
                "target": "email:nobody@example.com",
                "user_id": None,
                "tenant_id": tenant_ctx,
            }
        ]

    async def test_disabled_user_raises(self, tenant_ctx: str) -> None:
        user = _make_user(is_active=False)
        harness = _Harness(users=[user])

        with pytest.raises(AuthenticationError) as excinfo:
            await harness.service.login(LoginRequest(email=user.email, password="Password1!"))

        assert excinfo.value.message == LOGIN_FAILED_MESSAGE
        assert harness.token_svc.pairs_created == []
        assert harness.audit_svc.events == [
            {
                "action": "auth.login.failed",
                "target": f"user:{user.id}",
                "user_id": str(user.id),
                "tenant_id": tenant_ctx,
            }
        ]

    async def test_wrong_password_raises(self, tenant_ctx: str) -> None:
        user = _make_user()
        harness = _Harness(users=[user])

        with pytest.raises(AuthenticationError) as excinfo:
            await harness.service.login(LoginRequest(email=user.email, password="WrongPass1!"))

        assert excinfo.value.message == LOGIN_FAILED_MESSAGE
        assert harness.token_svc.pairs_created == []
        assert harness.audit_svc.events == [
            {
                "action": "auth.login.failed",
                "target": f"user:{user.id}",
                "user_id": str(user.id),
                "tenant_id": tenant_ctx,
            }
        ]

    async def test_all_failure_modes_raise_the_same_error(self, tenant_ctx: str) -> None:
        """
        Anti-enumeration invariant: every login failure is indistinguishable.

        Same exception type, same message - no account-existence oracle via
        error semantics.
        """
        disabled_user = _make_user(is_active=False)
        unverified_user = _make_user(is_verified=False)
        valid_user = _make_user()

        failures: list[tuple[_Harness, LoginRequest]] = [
            (_Harness(), LoginRequest(email="nobody@example.com", password="Password1!")),
            (
                _Harness(users=[disabled_user]),
                LoginRequest(email=disabled_user.email, password="Password1!"),
            ),
            (
                _Harness(users=[unverified_user]),
                LoginRequest(email=unverified_user.email, password="Password1!"),
            ),
            (
                _Harness(users=[valid_user]),
                LoginRequest(email=valid_user.email, password="WrongPass1!"),
            ),
        ]

        seen: set[tuple[type, str]] = set()
        for harness, request in failures:
            with pytest.raises(AuthenticationError) as excinfo:
                await harness.service.login(request)
            seen.add((type(excinfo.value), excinfo.value.message))

        assert seen == {(AuthenticationError, LOGIN_FAILED_MESSAGE)}


def _org_request(
    *,
    email: str = "owner@neworg.com",
    token: str = "vt",
    slug: str = "acme-inc",
) -> CreateOrganizationRequest:
    return CreateOrganizationRequest(
        email=email,
        verification_token=token,
        plan_id="professional",
        company_name="Acme Inc",
        industry="Technology",
        workspace_slug=slug,
        owner_full_name="New Owner",
        phone_country="US",
        phone_number="+15550123",
    )


class TestWizard:
    """The wizard's anti-abuse gate: one solved challenge, then a spent proof."""

    @staticmethod
    async def _clear_challenge(harness: _Harness, email: str = "owner@neworg.com") -> str:
        """Clear the wizard's one challenge and return the proof it mints."""
        started = await harness.service.signup_start(email=email, turnstile_token="tok")
        return str(started["flow_token"])

    async def test_signup_start_requires_valid_turnstile(self) -> None:
        harness = _Harness(turnstile=FakeTurnstile(result=False))

        with pytest.raises(ValidationError):
            await harness.service.signup_start(email="owner@neworg.com", turnstile_token="tok")

        assert harness.turnstile.calls == ["tok"]

    async def test_signup_start_passes_with_valid_turnstile(self) -> None:
        harness = _Harness()

        result = await harness.service.signup_start(email="owner@neworg.com", turnstile_token="tok")

        assert result["status"] == "ok"
        # The proof is what the rest of the wizard spends instead of a second
        # challenge, so it has to actually come back.
        flow_token = result["flow_token"]
        assert isinstance(flow_token, str) and flow_token
        flow = await harness.verification_store.get_signup_flow(flow_token)
        assert flow is not None
        assert flow.email == "owner@neworg.com"
        assert flow.sends == 0
        assert harness.turnstile.calls == ["tok"]

    async def test_wizard_costs_exactly_one_challenge(self) -> None:
        """The regression this whole change exists to prevent.

        A Turnstile token is single-use, so a second challenge seconds after the
        first is not a redundant round trip - it is the solve most likely to be
        scored as automation and rejected. The entire wizard must cost one solve.
        """
        harness = _Harness()
        flow_token = await self._clear_challenge(harness)

        sent = await harness.service.signup_send_code(
            email="owner@neworg.com", flow_token=flow_token
        )
        await harness.service.signup_send_code(email="owner@neworg.com", flow_token=flow_token)
        await harness.service.signup_verify_code(email="owner@neworg.com", code=sent["code"])

        assert harness.turnstile.calls == ["tok"]

    async def test_send_code_requires_the_flow_proof(self) -> None:
        """The endpoint that actually sends mail has to be gated, not just its entry.

        The gate is now a proof rather than a fresh challenge, but it is still a
        gate: a caller who never cleared the wizard cannot make it spend mail.
        """
        harness = _Harness()

        with pytest.raises(ValidationError):
            await harness.service.signup_send_code(
                email="owner@neworg.com", flow_token="never-issued"
            )

        # Nothing was minted, stored or sent.
        assert harness.email_svc.sent == []
        assert await harness.verification_store.get_otp_hash("owner@neworg.com") is None

    async def test_send_code_rejects_a_missing_flow_proof(self) -> None:
        """No proof at all is the shape of the request a script would send."""
        harness = _Harness()

        with pytest.raises(ValidationError):
            await harness.service.signup_send_code(email="owner@neworg.com", flow_token=None)

        assert harness.email_svc.sent == []

    async def test_flow_proof_is_bound_to_the_address_it_was_solved_for(self) -> None:
        """One solved challenge must not become mail to a stranger's inbox.

        This is the property the proof has to carry. While every send demanded
        its own challenge, solving one was worth exactly one address; now a
        single solve is reusable, so binding it to an address is what preserves
        that limit.
        """
        harness = _Harness()
        flow_token = await self._clear_challenge(harness, "owner@neworg.com")

        with pytest.raises(ValidationError):
            await harness.service.signup_send_code(
                email="someone-else@elsewhere.com", flow_token=flow_token
            )

        assert harness.email_svc.sent == []
        assert await harness.verification_store.get_otp_hash("someone-else@elsewhere.com") is None

    async def test_flow_proof_matches_the_address_case_insensitively(self) -> None:
        """The browser and the backend routinely disagree on address casing."""
        harness = _Harness()
        flow_token = await self._clear_challenge(harness, "owner@neworg.com")

        sent = await harness.service.signup_send_code(
            email="Owner@NewOrg.com", flow_token=flow_token
        )

        assert sent["status"] == "ok"

    async def test_flow_proof_stops_after_its_send_budget(self) -> None:
        """The ceiling that keeps one solve from becoming a mail cannon."""
        harness = _Harness()
        flow_token = await self._clear_challenge(harness)

        for attempt in range(settings.SIGNUP_FLOW_MAX_SENDS):
            # Step past the resend cooldown so each call really sends.
            harness.verification_store.now += settings.OTP_RESEND_COOLDOWN_SECONDS
            sent = await harness.service.signup_send_code(
                email="owner@neworg.com", flow_token=flow_token
            )
            assert sent["status"] == "ok", f"send {attempt} was refused"

        harness.verification_store.now += settings.OTP_RESEND_COOLDOWN_SECONDS
        with pytest.raises(ValidationError):
            await harness.service.signup_send_code(email="owner@neworg.com", flow_token=flow_token)

        assert len(harness.email_svc.sent) == settings.SIGNUP_FLOW_MAX_SENDS

    async def test_resend_cooldown_does_not_spend_the_proofs_budget(self) -> None:
        """A blocked resend sends no mail, so it must not cost the user a send.

        Otherwise a user who clicks resend inside the cooldown burns budget on a
        request that never sent anything, and is told to start over after one
        real code.
        """
        harness = _Harness()
        flow_token = await self._clear_challenge(harness)
        await harness.service.signup_send_code(email="owner@neworg.com", flow_token=flow_token)

        for _ in range(settings.SIGNUP_FLOW_MAX_SENDS - 1):
            blocked = await harness.service.signup_send_code(
                email="owner@neworg.com", flow_token=flow_token
            )
            assert blocked["code"] is None
            assert blocked["resend_in"] > 0

        flow = await harness.verification_store.get_signup_flow(flow_token)
        assert flow is not None
        assert flow.sends == 1

    async def test_send_code_checks_the_proof_before_honouring_the_resend_cooldown(self) -> None:
        """A blocked resend must not return 200 to a caller that proved nothing.

        Checking the cooldown first would hand a proofless caller a success
        response and a countdown, which reads as a working send and hides that
        nothing was verified.
        """
        harness = _Harness()
        flow_token = await self._clear_challenge(harness)
        await harness.service.signup_send_code(email="owner@neworg.com", flow_token=flow_token)

        with pytest.raises(ValidationError):
            await harness.service.signup_send_code(email="owner@neworg.com", flow_token=None)

        assert len(harness.email_svc.sent) == 1

    async def test_send_code_and_verify_flow(self) -> None:
        harness = _Harness()
        flow_token = await self._clear_challenge(harness)

        sent = await harness.service.signup_send_code(
            email="owner@neworg.com", flow_token=flow_token
        )
        assert sent["status"] == "ok"
        assert sent["resend_in"] == settings.OTP_RESEND_COOLDOWN_SECONDS
        assert sent["code"] is not None

        invalid = await harness.service.signup_verify_code(email="owner@neworg.com", code="000000")
        assert invalid["status"] == "invalid"
        assert invalid["verification_token"] is None
        assert await harness.verification_store.get_attempts("owner@neworg.com") == 1

        verified = await harness.service.signup_verify_code(
            email="owner@neworg.com", code=sent["code"]
        )
        assert verified["status"] == "ok"
        assert verified["verification_token"] is not None

    async def test_resend_blocked_within_cooldown(self) -> None:
        harness = _Harness()
        flow_token = await self._clear_challenge(harness)

        await harness.service.signup_send_code(email="owner@neworg.com", flow_token=flow_token)
        blocked = await harness.service.signup_send_code(
            email="owner@neworg.com", flow_token=flow_token
        )

        assert blocked["status"] == "ok"
        assert blocked["code"] is None
        assert blocked["resend_in"] == settings.OTP_RESEND_COOLDOWN_SECONDS
        assert len(harness.email_svc.sent) == 1

    async def test_otp_lockout_after_max_attempts(self) -> None:
        harness = _Harness()
        flow_token = await self._clear_challenge(harness)
        sent = await harness.service.signup_send_code(
            email="owner@neworg.com", flow_token=flow_token
        )
        code = sent["code"]
        assert code is not None

        for _ in range(settings.OTP_MAX_ATTEMPTS):
            result = await harness.service.signup_verify_code(
                email="owner@neworg.com", code="000000"
            )
            assert result["status"] == "invalid"

        locked = await harness.service.signup_verify_code(email="owner@neworg.com", code=code)
        assert locked["status"] == "invalid"
        assert locked["verification_token"] is None
        assert await harness.verification_store.get_otp_hash("owner@neworg.com") is None

    async def test_check_email_availability(self) -> None:
        harness = _Harness()
        assert (await harness.service.signup_check_email(email="fresh@example.com"))[
            "available"
        ] is True

        reserved = next(iter(RESERVED_EMAILS))
        assert (await harness.service.signup_check_email(email=reserved))["available"] is False

        existing = _make_user(tenant_id=uuid.uuid4(), email="taken@example.com")
        harness = _Harness(users=[existing])
        assert (await harness.service.signup_check_email(email="taken@example.com"))[
            "available"
        ] is False

    async def test_check_slug_availability_and_validation(self) -> None:
        harness = _Harness()
        assert (await harness.service.signup_check_slug(slug="my-workspace"))["available"] is True
        assert (await harness.service.signup_check_slug(slug="  My-Workspace  "))[
            "available"
        ] is True
        assert (await harness.service.signup_check_slug(slug="bad_slug!"))["available"] is False
        assert (await harness.service.signup_check_slug(slug=""))["available"] is False

        reserved = next(iter(RESERVED_SLUGS))
        assert (await harness.service.signup_check_slug(slug=reserved))["available"] is False

        existing = Tenant(name="Existing", slug="existing", id=uuid.uuid4())
        harness = _Harness(tenants=[existing])
        assert (await harness.service.signup_check_slug(slug="existing"))["available"] is False

    async def test_set_password_enforces_policy(self) -> None:
        harness = _Harness()

        with pytest.raises(ValidationError):
            await harness.service.signup_set_password(
                email="owner@neworg.com",
                verification_token="vt",
                password="short",
                captcha_id="cap",
                captcha_answer="ABCDE",
            )
        with pytest.raises(ValidationError):
            await harness.service.signup_set_password(
                email="owner@neworg.com",
                verification_token="vt",
                password="alllowercase1!",
                captcha_id="cap",
                captcha_answer="ABCDE",
            )

    async def test_set_password_rejects_invalid_captcha(self) -> None:
        harness = _Harness(captcha_store=FakeCaptchaStore(valid=False))
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "")

        with pytest.raises(ValidationError):
            await harness.service.signup_set_password(
                email="owner@neworg.com",
                verification_token="vt",
                password="ValidPass123!",
                captcha_id="cap",
                captcha_answer="WRONG",
            )
        assert harness.captcha_store.verifications == [("cap", "WRONG")]
        payload = await harness.verification_store.get_verification_token("vt")
        assert payload is not None
        assert payload["password_hash"] == ""

    async def test_set_password_stores_hash(self) -> None:
        harness = _Harness()
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "")

        await harness.service.signup_set_password(
            email="owner@neworg.com",
            verification_token="vt",
            password="ValidPass123!",
            captcha_id="cap",
            captcha_answer="ABCDE",
        )

        assert harness.captcha_store.verifications == [("cap", "ABCDE")]
        payload = await harness.verification_store.get_verification_token("vt")
        assert payload is not None
        assert payload["password_hash"] != "ValidPass123!"

    async def test_full_wizard_provisions_verified_owner(self) -> None:
        harness = _Harness()
        flow_token = await self._clear_challenge(harness)
        sent = await harness.service.signup_send_code(
            email="owner@neworg.com", flow_token=flow_token
        )
        code = sent["code"]
        assert code is not None
        vt = (await harness.service.signup_verify_code(email="owner@neworg.com", code=code))[
            "verification_token"
        ]
        assert vt is not None
        await harness.service.signup_set_password(
            email="owner@neworg.com",
            verification_token=vt,
            password="ValidPass123!",
            captcha_id="cap",
            captcha_answer="ABCDE",
        )

        result = await harness.service.signup_create_organization(
            _org_request(token=vt), ip_address=None, user_agent=None
        )

        assert result["status"] == "ok"
        assert result["mfa_required"] is True
        assert result["tenant_slug"] == "acme-inc"

        assert len(harness.tenant_repo.created) == 1
        tenant = harness.tenant_repo.created[0]
        assert tenant.name == "Acme Inc"
        assert tenant.slug == "acme-inc"
        assert tenant.plan_tier == "pro"
        assert tenant.industry == "Technology"
        assert tenant.is_active is True

        roles = {role.name: role for role in harness.role_repo.created}
        assert set(roles) == {name for name, _ in SYSTEM_ROLE_DEFINITIONS}

        assert len(harness.user_repo.created) == 1
        user = harness.user_repo.created[0]
        assert user.email == "owner@neworg.com"
        assert user.full_name == "New Owner"
        assert user.is_active is True
        assert user.is_verified is True
        assert user.phone_country == "US"
        assert user.phone_number == "+15550123"

        owner_role = roles["tenant_owner"]
        assert harness.role_repo.grants == [
            (str(user.id), str(owner_role.id), str(tenant.id), str(tenant.id))
        ]

        assert len(harness.membership_svc.active) == 1
        membership = harness.membership_svc.active[0]
        assert membership.user_id == user.id
        assert membership.tenant_id == tenant.id
        assert membership.role_id == owner_role.id
        assert membership.status == MembershipStatus.ACTIVE

        assert await harness.verification_store.get_verification_token(vt) is not None
        assert harness.audit_svc.events == [
            {
                "action": "auth.register.success",
                "target": f"user:{user.id}",
                "user_id": str(user.id),
                "tenant_id": str(tenant.id),
            }
        ]
        assert harness.email_svc.sent == [{"to": "owner@neworg.com", "code": code}]

    async def test_create_organization_requires_password_first(self) -> None:
        harness = _Harness()
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "")

        with pytest.raises(TokenInvalidError):
            await harness.service.signup_create_organization(
                _org_request(), ip_address=None, user_agent=None
            )

        assert harness.tenant_repo.created == []
        assert harness.user_repo.created == []

    async def test_create_organization_rejects_token_email_mismatch(self) -> None:
        harness = _Harness()
        await harness.verification_store.set_verification_token("vt", "other@example.com", "hash")

        with pytest.raises(TokenInvalidError):
            await harness.service.signup_create_organization(
                _org_request(email="owner@neworg.com"), ip_address=None, user_agent=None
            )

    async def test_create_organization_rejects_invalid_slug(self) -> None:
        harness = _Harness()
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "hash")

        with pytest.raises(ValidationError):
            await harness.service.signup_create_organization(
                _org_request(slug="Bad_Slug!"), ip_address=None, user_agent=None
            )

    async def test_create_organization_rejects_taken_slug(self) -> None:
        existing = Tenant(name="Acme", slug="acme-inc", id=uuid.uuid4())
        harness = _Harness(tenants=[existing])
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "hash")

        with pytest.raises(ConflictError):
            await harness.service.signup_create_organization(
                _org_request(), ip_address=None, user_agent=None
            )

        assert harness.user_repo.created == []

    async def test_create_organization_rejects_taken_email(self) -> None:
        existing = _make_user(tenant_id=uuid.uuid4(), email="owner@neworg.com")
        harness = _Harness(users=[existing])
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "hash")

        with pytest.raises(UserAlreadyExistsError):
            await harness.service.signup_create_organization(
                _org_request(), ip_address=None, user_agent=None
            )

    async def test_create_organization_captures_billing_address(self) -> None:
        harness = _Harness()
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "hash")

        request = _org_request()
        request.address = BillingAddress(
            country="US",
            address_line1="1 Main St",
            address_line2="Apt 2",
            city="Springfield",
            state="IL",
            postal_code="62704",
        )
        await harness.service.signup_create_organization(request, ip_address=None, user_agent=None)

        tenant = harness.tenant_repo.created[0]
        assert tenant.billing_address == {
            "country": "US",
            "addressLine1": "1 Main St",
            "addressLine2": "Apt 2",
            "city": "Springfield",
            "state": "IL",
            "postalCode": "62704",
        }

    async def test_create_organization_defaults_plan_id_to_starter(self) -> None:
        """The org step runs before the Plan step, so plan_id defaults to starter."""
        request = CreateOrganizationRequest(
            email="owner@neworg.com",
            verification_token="vt",
            company_name="Acme Inc",
            industry="Technology",
            workspace_slug="acme-inc",
            owner_full_name="New Owner",
        )
        assert request.plan_id == "starter"

        harness = _Harness()
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "hash")
        await harness.service.signup_create_organization(request, ip_address=None, user_agent=None)

        tenant = harness.tenant_repo.created[0]
        assert tenant.plan_tier == "starter"


class TestResolveSignupCheckoutTenant:
    """resolve_signup_checkout_tenant: token + tenant-membership authorization."""

    async def test_returns_tenant_for_valid_token_and_member(self) -> None:
        tenant = Tenant(name="Acme", slug="acme-inc", id=uuid.uuid4())
        owner = _make_user(tenant_id=tenant.id, email="owner@neworg.com")
        harness = _Harness(users=[owner], tenants=[tenant])
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "hash")

        resolved = await harness.service.resolve_signup_checkout_tenant(
            email="owner@neworg.com",
            verification_token="vt",
            tenant_id=tenant.id,
        )

        assert resolved is tenant

    async def test_rejects_expired_or_unknown_token(self) -> None:
        tenant = Tenant(name="Acme", slug="acme-inc", id=uuid.uuid4())
        harness = _Harness(tenants=[tenant])

        with pytest.raises(TokenInvalidError, match="Verification session"):
            await harness.service.resolve_signup_checkout_tenant(
                email="owner@neworg.com",
                verification_token="missing",
                tenant_id=tenant.id,
            )

    async def test_rejects_token_email_mismatch(self) -> None:
        tenant = Tenant(name="Acme", slug="acme-inc", id=uuid.uuid4())
        harness = _Harness(tenants=[tenant])
        await harness.verification_store.set_verification_token("vt", "other@example.com", "hash")

        with pytest.raises(TokenInvalidError, match="Verification session"):
            await harness.service.resolve_signup_checkout_tenant(
                email="owner@neworg.com",
                verification_token="vt",
                tenant_id=tenant.id,
            )

    async def test_rejects_unknown_tenant(self) -> None:
        harness = _Harness()
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "hash")

        with pytest.raises(TokenInvalidError, match="Verification session"):
            await harness.service.resolve_signup_checkout_tenant(
                email="owner@neworg.com",
                verification_token="vt",
                tenant_id=uuid.uuid4(),
            )

    async def test_rejects_email_not_member_of_tenant(self) -> None:
        """A valid token cannot mint a checkout for a tenant the email lacks."""
        tenant = Tenant(name="Acme", slug="acme-inc", id=uuid.uuid4())
        other = Tenant(name="Other", slug="other", id=uuid.uuid4())
        outsider = _make_user(tenant_id=other.id, email="owner@neworg.com")
        harness = _Harness(users=[outsider], tenants=[tenant, other])
        await harness.verification_store.set_verification_token("vt", "owner@neworg.com", "hash")

        with pytest.raises(TokenInvalidError, match="Verification session"):
            await harness.service.resolve_signup_checkout_tenant(
                email="owner@neworg.com",
                verification_token="vt",
                tenant_id=tenant.id,
            )
