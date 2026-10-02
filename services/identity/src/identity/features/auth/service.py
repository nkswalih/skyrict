"""Authentication feature services - login/register and the token lifecycle.

``AuthenticationService`` authenticates users, self-service provisions new
tenants, and verifies emails; ``TokenService`` owns the JWT lifecycle (create,
refresh, revoke, introspect). Both live in this feature because they model the
same domain.

The tenant is resolved ONCE by the middleware (Host subdomain in production,
X-Tenant-Slug in dev) and consumed from TenantContext - except self-service
registration, which runs without a routed tenant (the request bypasses tenant
resolution via SKIP_AUTH_PATHS) and provisions its own.
"""

from __future__ import annotations

import hmac
import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from identity.core.audit_events import AUTH_REFRESH_REUSE_DETECTED, AUTH_REFRESH_SUCCESS
from identity.core.config import Environment, settings
from identity.core.console_urls import security_console_base_url
from identity.core.constants import (
    LOGIN_FAILED_MESSAGE,
    RESERVED_EMAILS,
    RESERVED_SLUGS,
    SYSTEM_ROLE_DEFINITIONS,
)
from identity.core.email import EmailService
from identity.core.email_templates import SecurityAlert
from identity.core.geolocation import format_location, geoip, mask_ip
from identity.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    mfa_is_required,
    validate_password_policy,
    verify_jwt,
    verify_password,
)
from identity.core.tenant_context import TenantContext
from identity.core.turnstile import TurnstileVerifier
from identity.core.user_agent import parse_client_hints, parse_user_agent
from identity.domain.entities import Role, Session, SessionStatus, Tenant, User
from identity.domain.value_objects import TokenPair
from identity.events.producers.tenant_events import emit_tenant_provisioned
from identity.features.auth.captcha.captcha_store import CaptchaStore
from identity.features.auth.mfa_challenge_store import MfaChallengeStore
from identity.features.auth.verification_store import (
    VerificationStore,
    generate_otp,
    generate_signup_flow_token,
    generate_verification_token,
    hash_otp,
)
from identity.features.billing.plans import resolve_tier
from skyrict_common.exceptions import (
    AuthenticationError,
    ConflictError,
    SessionNotFoundError,
    TokenExpiredError,
    TokenInvalidError,
    TokenReuseDetectedError,
    UserAlreadyExistsError,
    ValidationError,
)

if TYPE_CHECKING:
    from identity.features.audit.service import AuditService
    from identity.features.auth.schemas import (
        CreateOrganizationRequest,
        LoginRequest,
    )
    from identity.features.memberships.service import MembershipService
    from identity.features.organizations.ports import TenantRepositoryPort
    from identity.features.roles.ports import RoleRepositoryPort
    from identity.features.sessions.service import SessionService
    from identity.features.users.ports import UserRepositoryPort

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# A valid Argon2id hash of a throwaway value, verified against on the
# unknown-email path so response TIME is indistinguishable from the
# wrong-password path (anti-enumeration via the timing side-channel).
# Computed once at import - the one-time cost is paid at process start.
_DUMMY_PASSWORD_HASH = hash_password("anti-enumeration-timing-dummy")


def _validate_wizard_password(password: str) -> None:
    validate_password_policy(password)


def _normalize_slug(slug: str) -> str | None:
    normalized = slug.strip().lower()
    if not _SLUG_RE.fullmatch(normalized):
        return None
    return normalized


def _compare_otp(provided: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(provided), expected_hash)


class AuthenticationService:
    """Handles user authentication, provisioning, and email verification."""

    def __init__(
        self,
        user_repo: UserRepositoryPort,
        tenant_repo: TenantRepositoryPort,
        role_repo: RoleRepositoryPort,
        token_service: TokenService,
        audit_service: AuditService,
        email_service: EmailService,
        session_service: SessionService,
        membership_service: MembershipService,
        verification_store: VerificationStore | None = None,
        turnstile: TurnstileVerifier | None = None,
        mfa_challenge_store: MfaChallengeStore | None = None,
        captcha_store: CaptchaStore | None = None,
    ) -> None:
        self.user_repo = user_repo
        self.tenant_repo = tenant_repo
        self.role_repo = role_repo
        self.token_service = token_service
        self.audit_service = audit_service
        self.email_service = email_service
        self.session_service = session_service
        self.membership_service = membership_service
        self.verification_store = verification_store or VerificationStore()
        self.turnstile = turnstile or TurnstileVerifier()
        self.mfa_challenge_store = mfa_challenge_store or MfaChallengeStore()
        self.captcha_store = captcha_store or CaptchaStore()

    async def login(
        self,
        request: LoginRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        client_hints: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Authenticate a user and return a token pair (plus MFA posture).

        Anti-enumeration contract (ADR-004): every failure mode raises the
        SAME :class:`AuthenticationError` with the same message, and every
        attempt performs exactly one Argon2id verification (a dummy one for
        unknown emails), so neither the response NOR its timing reveals
        whether an account exists, is disabled, or is unverified. Failed
        attempts are audited for brute-force / credential-stuffing monitoring.

        Raises:
            AuthenticationError: For any failed authentication - unknown
                email, disabled or unverified account, or wrong password.
        """
        tenant_id = TenantContext.get()

        # Emails are unique per tenant, so lookups are tenant-scoped.
        user = await self.user_repo.get_by_email(tenant_id, request.email)
        if not user:
            # Dummy verification keeps timing uniform: an unknown email is as
            # slow as a wrong password, so latency cannot be used to probe
            # which accounts exist.
            verify_password(request.password, _DUMMY_PASSWORD_HASH)
            await self._log_login_failure(
                email=request.email,
                user_id=None,
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=tenant_id,
            )
            raise AuthenticationError(LOGIN_FAILED_MESSAGE)

        if not verify_password(request.password, user.password_hash):
            await self._log_login_failure(
                email=request.email,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=tenant_id,
            )
            raise AuthenticationError(LOGIN_FAILED_MESSAGE)

        # Account-state gates run AFTER password verification so every failure
        # path costs exactly one Argon2id - no state oracle via timing either.
        if not user.is_active:
            await self._log_login_failure(
                email=request.email,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=tenant_id,
            )
            raise AuthenticationError(LOGIN_FAILED_MESSAGE)

        # Verification gate: unverified accounts cannot sign in.
        if not user.is_verified:
            await self._log_login_failure(
                email=request.email,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=tenant_id,
            )
            raise AuthenticationError(LOGIN_FAILED_MESSAGE)

        assert user.id is not None

        if user.mfa_enabled:
            mfa_token = await self.mfa_challenge_store.create(
                user_id=str(user.id),
                tenant_id=tenant_id,
            )
            await self.audit_service.log(
                action="auth.login.mfa_challenged",
                target=f"user:{user.id}",
                user_id=str(user.id),
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return {
                "access_token": None,
                "refresh_token": None,
                "token_type": "Bearer",
                "expires_in": 0,
                "mfa_required": True,
                "mfa_token": mfa_token,
                "next_step": "mfa.verify",
                "user": user,
            }

        # Forced MFA: every account without MFA enabled must enroll, regardless
        # of role or tenant policy. The flag clears only once MFA is actually
        # enabled, so tokens issued now are gated until then.
        mfa_required = mfa_is_required(mfa_enabled=False)

        result = await self.complete_authenticated_login(
            user=user,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
            client_hints=client_hints,
        )
        result["mfa_required"] = mfa_required
        result["next_step"] = "mfa.setup" if mfa_required else None
        return result

    async def complete_authenticated_login(
        self,
        *,
        user: User,
        tenant_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        client_hints: dict[str, str] | None = None,
        audit_action: str = "auth.login.success",
    ) -> dict[str, Any]:
        """Issue a fresh token pair + session and audit the completed login."""

        assert user.id is not None

        session_id = uuid.uuid4()
        tokens = await self.token_service.create_token_pair(
            user_id=str(user.id),
            tenant_id=tenant_id,
            session_id=str(session_id),
        )

        device = parse_user_agent(
            user_agent,
            hints=parse_client_hints(client_hints),
        )
        location = geoip.lookup(ip_address)
        device_info = {
            "browser": device.browser,
            "browser_version": device.browser_version,
            "os": device.os,
            "os_version": device.os_version,
            "device": device.device,
            "device_type": device.device_type,
            "browser_name": device.browser_name,
            "os_name": device.os_name,
            "device_family": device.device_family,
            "device_model": device.device_model,
            "user_agent": user_agent,
        }

        new_device = not await self.session_service.has_prior_device(
            user.id,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self.session_service.create_session(
            session_id=session_id,
            user_id=user.id,
            tenant_id=uuid.UUID(tenant_id),
            refresh_token_hash=hash_refresh_token(tokens.refresh_token),
            user_agent=user_agent,
            ip_address=ip_address,
            device_info=device_info,
            location=format_location(location),
        )

        await self.audit_service.log(
            action=audit_action,
            target=f"user:{user.id}",
            user_id=str(user.id),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if new_device:
            tenant = await self.tenant_repo.get_by_id(tenant_id)
            base = security_console_base_url(tenant_slug=tenant.slug if tenant else None)
            await self.email_service.send_security_alert(
                alert=SecurityAlert(
                    to=user.email,
                    full_name=user.full_name,
                    event_type="new_device",
                    ip_address=mask_ip(ip_address),
                    location=format_location(location),
                    browser=" ".join(p for p in (device.browser, device.browser_version) if p)
                    or "Unknown",
                    os=" ".join(p for p in (device.os, device.os_version) if p) or "Unknown",
                    device=f"{device.device} ({device.device_type})",
                    auth_method=(
                        "Password + MFA"
                        if audit_action == "auth.login.mfa_verified"
                        else "Password"
                    ),
                    session_id_masked=f"{str(session_id)[:8]}••••",
                    date_time=datetime.now(UTC).strftime("%b %d, %Y at %I:%M %p UTC"),
                    review_url=f"{base}/settings/security" if base else None,
                    secure_url=f"{base}/settings/security/password" if base else None,
                    support_email=settings.SECURITY_SUPPORT_EMAIL,
                )
            )

        return {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in,
            "mfa_required": False,
            "next_step": None,
            "user": user,
        }

    async def _log_login_failure(
        self,
        *,
        email: str,
        user_id: str | uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        tenant_id: str,
    ) -> None:
        """Record a failed login for brute-force / credential-stuffing monitoring.

        Unknown emails are targeted as ``email:<address>`` (no user row
        exists); known accounts as ``user:<id>``. The attempted email is the
        point of the event - it is what an incident response would search on.
        """
        await self.audit_service.log(
            action="auth.login.failed",
            target=f"user:{user_id}" if user_id is not None else f"email:{email}",
            user_id=str(user_id) if user_id is not None else None,
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=tenant_id,
        )

    async def signup_start(self, *, email: str, turnstile_token: str | None) -> dict[str, Any]:
        """Open the wizard: the one place the user proves they are not a robot.

        Solving it hands back a short-lived proof that the rest of the wizard
        spends instead of solving a second challenge. The proof is minted *for
        this address*, so one solve cannot be turned into mail to someone else's
        inbox, and it carries a small send budget so it cannot be used to flood
        a single address either.
        """
        ok = await self.turnstile.verify(turnstile_token)
        if not ok:
            raise ValidationError("Unable to verify you are not a robot. Try again.")
        flow_token = generate_signup_flow_token()
        await self.verification_store.set_signup_flow(flow_token, email)
        return {"status": "ok", "flow_token": flow_token}

    async def signup_send_code(self, *, email: str, flow_token: str | None) -> dict[str, Any]:
        # Proof first, before the resend check, not after it.
        #
        # Checking after would let a caller who never cleared the wizard's
        # challenge consume a resend slot and get a 200 with only a countdown,
        # which reads as success and hides the fact that nothing was verified.
        flow = (
            await self.verification_store.get_signup_flow(flow_token)
            if flow_token is not None
            else None
        )
        if flow_token is None or flow is None or flow.email.lower() != email.lower():
            raise ValidationError(
                "This sign-up session has expired. Go back to step 1 and start again."
            )
        if flow.sends >= settings.SIGNUP_FLOW_MAX_SENDS:
            raise ValidationError("Too many codes requested. Go back to step 1 and start again.")
        if await self.verification_store.is_resend_blocked(email):
            return {
                "status": "ok",
                "resend_in": await self.verification_store.resend_in(email),
                "code": None,
            }
        # Charged here, not on entry: a cooldown that returned no mail must not
        # cost the user part of their budget.
        await self.verification_store.consume_signup_flow_send(flow_token)
        code = generate_otp()
        await self.verification_store.set_otp(email, hash_otp(code))
        await self.verification_store.mark_resend(email)
        await self.email_service.send_otp(to=email, code=code)
        return {
            "status": "ok",
            "resend_in": settings.OTP_RESEND_COOLDOWN_SECONDS,
            # Plaintext code only in TEST so integration tests can drive the
            # wizard; dev/staging/production deliver it solely via email.
            "code": code if settings.ENVIRONMENT == Environment.TEST else None,
        }

    async def signup_verify_code(self, *, email: str, code: str) -> dict[str, Any]:
        if await self.verification_store.get_attempts(email) >= settings.OTP_MAX_ATTEMPTS:
            await self.verification_store.delete_otp(email)
            return {"status": "invalid", "verification_token": None}
        stored_hash = await self.verification_store.get_otp_hash(email)
        if stored_hash is None:
            return {"status": "invalid", "verification_token": None}
        if not _compare_otp(code, stored_hash):
            await self.verification_store.increment_attempts(email)
            return {"status": "invalid", "verification_token": None}
        await self.verification_store.delete_otp(email)
        token = generate_verification_token()
        await self.verification_store.set_verification_token(token, email, "")
        return {"status": "ok", "verification_token": token}

    async def signup_set_password(
        self,
        *,
        email: str,
        verification_token: str,
        password: str,
        captcha_id: str,
        captcha_answer: str,
    ) -> dict[str, Any]:
        _validate_wizard_password(password)
        if not await self.captcha_store.verify(captcha_id, captcha_answer):
            raise ValidationError("Unable to verify the security code. Try again.")
        await self._require_verification_token(verification_token, email)
        await self.verification_store.update_verification_token_password(
            verification_token, hash_password(password)
        )
        return {"status": "ok"}

    async def signup_check_email(self, *, email: str) -> dict[str, Any]:
        normalized = email.lower().strip()
        available = not await self.user_repo.email_exists_global(normalized)
        available = available and normalized not in RESERVED_EMAILS
        return {"available": available}

    async def signup_check_slug(self, *, slug: str) -> dict[str, Any]:
        normalized = _normalize_slug(slug)
        if normalized is None or normalized in RESERVED_SLUGS:
            return {"available": False}
        if await self.tenant_repo.slug_exists(normalized):
            return {"available": False}
        return {"available": True}

    async def signup_create_organization(
        self, request: CreateOrganizationRequest, *, ip_address: str | None, user_agent: str | None
    ) -> dict[str, Any]:
        payload = await self._require_verification_token(request.verification_token, request.email)
        if not payload["password_hash"]:
            raise TokenInvalidError("Password has not been set for this session")
        slug = _normalize_slug(request.workspace_slug)
        if slug is None:
            raise ValidationError(
                "Workspace slug may only contain lowercase letters, numbers, and hyphens"
            )
        if slug in RESERVED_SLUGS or await self.tenant_repo.slug_exists(slug):
            raise ConflictError("This workspace URL is already taken")
        if await self.user_repo.email_exists_global(request.email):
            raise UserAlreadyExistsError()

        tenant_id = uuid.uuid4()
        trial_ends_at = datetime.now(UTC) + timedelta(days=settings.BILLING_TRIAL_DAYS)
        await self.tenant_repo.create(
            Tenant(
                name=request.company_name,
                slug=slug,
                plan_tier=resolve_tier(request.plan_id),
                industry=request.industry,
                billing_address=self._billing_address_payload(request),
                trial_ends_at=trial_ends_at,
                subscription_status="trialing",
                id=tenant_id,
            )
        )

        roles = await self._create_system_roles(tenant_id)
        owner_role = roles["tenant_owner"]

        user = await self.user_repo.create(
            User(
                tenant_id=tenant_id,
                email=request.email,
                password_hash=payload["password_hash"],
                full_name=request.owner_full_name,
                is_active=True,
                is_verified=True,
                phone_country=request.phone_country,
                phone_number=request.phone_number,
            )
        )

        assert user.id is not None
        assert owner_role.id is not None

        await self.role_repo.grant_to_user(
            user_id=user.id,
            role_id=owner_role.id,
            tenant_id=tenant_id,
            scope_id=tenant_id,
        )

        await self.membership_service.create_active(
            tenant_id=tenant_id,
            user_id=user.id,
            role_id=owner_role.id,
            invited_email=request.email,
        )

        await self.audit_service.log(
            action="auth.register.success",
            target=f"user:{user.id}",
            user_id=str(user.id),
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=str(tenant_id),
        )

        # The verification token is intentionally KEPT: the wizard still has
        # Plan and Billing steps ahead, and the checkout-session endpoint reuses
        # this token as the credential. It remains short-lived (TTL-bounded in
        # the store) and single-email-bound, so retention does not weaken the
        # wizard's replay protections.

        role_grants = [
            {
                "role_id": str(role.id),
                "role_name": role.name,
                "permissions": role.permissions,
                "is_system_role": role.is_system_role,
                "user_id": str(user.id) if role.name == "tenant_owner" else None,
                "scope_id": str(tenant_id) if role.name == "tenant_owner" else None,
            }
            for role in roles.values()
            if role.id is not None
        ]
        await emit_tenant_provisioned(
            tenant_id=tenant_id,
            slug=slug,
            role_grants=role_grants,
        )

        return {
            "status": "ok",
            "mfa_required": True,
            "tenant_id": tenant_id,
            "tenant_slug": slug,
            "subscription_status": "trialing",
            "trial_ends_at": trial_ends_at,
        }

    async def resolve_signup_checkout_tenant(
        self, *, email: str, verification_token: str, tenant_id: str | uuid.UUID
    ) -> Tenant:
        """Authorize a signup Checkout session against a provisioned tenant.

        The wizard Plan/Billing steps run after the tenant exists but before
        the owner has an account, so regular auth dependencies cannot guard
        the checkout endpoint. Authorization is two-factor:

        1. the verification token must still be bound to ``email`` (the token
           is the credential minted at the verify-code step), and
        2. the email must own a user inside ``tenant_id`` - so a valid token
           cannot be used to mint a Checkout session for a tenant the caller
           does not belong to.

        Raises:
            TokenInvalidError: the token is missing/mismatched, the tenant is
                unknown, or the email is not a member of the tenant (401).
        """
        await self._require_verification_token(verification_token, email)
        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if tenant is None:
            raise TokenInvalidError("Verification session is invalid or expired")
        assert tenant.id is not None  # loaded from the repo
        user = await self.user_repo.get_by_email(tenant.id, email)
        if user is None:
            raise TokenInvalidError("Verification session is invalid or expired")
        return tenant

    async def _require_verification_token(self, token: str, email: str) -> dict[str, str]:
        payload = await self.verification_store.get_verification_token(token)
        if payload is None or payload["email"].lower() != email.lower():
            raise TokenInvalidError("Verification session is invalid or expired")
        return payload

    @staticmethod
    def _billing_address_payload(request: CreateOrganizationRequest) -> dict[str, Any] | None:
        if request.address is None:
            return None
        address = request.address
        return {
            "country": address.country,
            "addressLine1": address.address_line1,
            "addressLine2": address.address_line2,
            "city": address.city,
            "state": address.state,
            "postalCode": address.postal_code,
        }

    async def _create_system_roles(self, tenant_id: uuid.UUID) -> dict[str, Role]:
        """Provision the platform-defined system roles for a tenant."""
        roles: dict[str, Role] = {}
        for name, permissions in SYSTEM_ROLE_DEFINITIONS:
            role = await self.role_repo.create(
                Role(
                    tenant_id=tenant_id,
                    name=name,
                    permissions=list(permissions),
                    is_system_role=True,
                )
            )
            roles[name] = role
        return roles


class TokenService:
    """Manages JWT token lifecycle - creation, refresh, revocation.

    Session lifecycle (family tracking, expiry materialization, revocation)
    is delegated to ``SessionService``; this service owns only token mechanics.
    """

    def __init__(self, session_service: SessionService, audit_service: AuditService) -> None:
        self.session_service = session_service
        self.audit_service = audit_service

    async def create_token_pair(
        self,
        *,
        user_id: str,
        tenant_id: str,
        session_id: str | None = None,
    ) -> TokenPair:
        """Create an access + refresh token pair."""
        access_token = create_access_token(user_id, tenant_id=tenant_id)
        refresh_token = create_refresh_token(user_id, tenant_id=tenant_id, session_id=session_id)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenPair:
        """Validate a refresh token, rotate it, and issue a new pair."""
        payload = verify_jwt(refresh_token)

        if payload.get("type") != "refresh":
            raise TokenInvalidError("Token is not a refresh token")

        user_id = payload["sub"]
        tenant_id = payload["tenant_id"]
        session_id = payload.get("session_id")

        session = await self.session_service.get_session(session_id) if session_id else None

        # A session is bound to one tenant at creation. The token's tenant_id
        # claim must match the stored session tenant, or the refresh is an
        # access violation - not token reuse - so it is rejected cleanly
        # instead of arming the family chain-kill side effects.
        if session is not None and session.tenant_id != uuid.UUID(tenant_id):
            raise TokenInvalidError("Session does not belong to this tenant")

        # A terminal session was already handled when it died - a client
        # retrying that refresh token is rejected quietly so the reuse handler
        # (family revoke + audit log) is not re-armed on every retry. Reuse of
        # a rotated token is only EVER tolerated inside the grace window - a
        # dead session is already beyond it, so the reuse-detect stays.
        if session is not None and session.status is not SessionStatus.ACTIVE:
            raise TokenReuseDetectedError()

        now = datetime.now(UTC)
        presented_hash = hash_refresh_token(refresh_token)
        # A benign race (two tabs, a dropped response) re-sends the token that
        # was rotated out milliseconds ago. Accept and re-rotate it inside the
        # grace window instead of treating the whole family as stolen.
        within_grace = (
            session is not None
            and session.previous_refresh_token_hash == presented_hash
            and session.previous_token_valid_until is not None
            and now <= session.previous_token_valid_until
        )

        if (
            session is None
            or session.user_id != uuid.UUID(user_id)
            or session.refresh_token_hash != presented_hash
        ) and not within_grace:
            await self._handle_reuse(user_id=user_id, tenant_id=tenant_id, session=session)
            raise TokenReuseDetectedError()

        # within_grace implies a stored session, so past the guard above there
        # must be one to rotate against.
        assert session is not None
        assert session.id is not None
        if session.expires_at <= now:
            await self.session_service.expire_session(session.id, tenant_id=tenant_id)
            raise TokenExpiredError()

        # What the session remembers as its grace token after this rotation.
        #
        # A grace replay must NOT overwrite the remembered token. The presented
        # token is the one the window exists to protect; storing the token that
        # was just consumed instead narrows the window on every concurrent
        # replay, so a K-way race (two tabs, a dropped response, the page
        # hydrating while the test client hydrates the same cookie) walks the
        # presented value two generations behind the record and the last replay
        # is classified as theft - which revokes the whole family with no
        # recovery. Keeping the remembered token instead makes the window
        # sticky: any number of overlapping replays of the same cookie stay
        # inside one rotation.
        #
        # The deadline is carried forward UNCHANGED. It is anchored to when the
        # protected token was retired, so a caller cannot extend its own
        # tolerance by replaying - otherwise a captured refresh token would
        # stay replayable for as long as its holder kept presenting it, which is
        # exactly the persistence this window exists to bound. Replays still
        # collapse into the window because the concurrent ones are the race
        # itself: they arrive together, well inside the original deadline.
        if within_grace:
            # `within_grace` matched on a non-null previous hash and a non-null
            # deadline, so both values below are the ones the window guards.
            carried_hash = session.previous_refresh_token_hash
            previous_valid_until = session.previous_token_valid_until
        else:
            carried_hash = session.refresh_token_hash
            previous_valid_until = now + timedelta(seconds=settings.REFRESH_REUSE_GRACE_SECONDS)

        tokens = await self.create_token_pair(
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
        )
        rotated = await self.session_service.rotate_session(
            session.id,
            refresh_token_hash=hash_refresh_token(tokens.refresh_token),
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            tenant_id=tenant_id,
            previous_refresh_token_hash=carried_hash,
            previous_token_valid_until=previous_valid_until,
        )
        assert rotated is not None and rotated.id is not None
        await self.audit_service.log(
            action=AUTH_REFRESH_SUCCESS,
            target=f"session:{rotated.id}",
            user_id=user_id,
            tenant_id=tenant_id,
        )
        return tokens

    async def _handle_reuse(
        self,
        *,
        user_id: str,
        tenant_id: str,
        session: Session | None,
    ) -> None:
        """Revoke the token's family (or all the user's sessions when unknown).

        Reuse of a rotated token is the signature of a stolen refresh token, so
        the whole chain that token belongs to is killed, not just one session.
        """
        if session is not None and session.token_family_id is not None:
            await self.session_service.revoke_family(
                session.token_family_id,
                tenant_id=session.tenant_id,
            )
        else:
            await self.session_service.revoke_all_sessions(user_id)
        await self.audit_service.log(
            action=AUTH_REFRESH_REUSE_DETECTED,
            target=f"session:{session.id if session else None}",
            user_id=user_id,
            tenant_id=tenant_id,
        )
        await self.session_service.commit()

    async def revoke_token(self, refresh_token: str) -> None:
        """Revoke a refresh token (invalidate the session)."""
        payload = verify_jwt(refresh_token)
        if payload.get("type") != "refresh":
            raise TokenInvalidError("Token is not a refresh token")

        user_id = payload["sub"]
        tenant_id = payload["tenant_id"]
        session_id = payload.get("session_id")
        session = (
            await self.session_service.get_session(session_id, tenant_id=tenant_id)
            if session_id
            else None
        )
        if session is not None and session.id is not None and session.user_id == uuid.UUID(user_id):
            # Idempotent logout - already-revoked sessions are fine.
            with suppress(SessionNotFoundError):
                await self.session_service.revoke_session(user_id, session.id, tenant_id=tenant_id)

    async def introspect(self, token: str) -> dict[str, Any]:
        """Introspect a token - return its claims if valid."""
        try:
            payload = verify_jwt(token)
            return {
                "active": True,
                "sub": payload.get("sub"),
                "tenant_id": payload.get("tenant_id"),
                "type": payload.get("type"),
                "exp": payload.get("exp"),
            }
        except (TokenExpiredError, TokenInvalidError):
            return {"active": False}
