"""Auth endpoints - login, onboarding wizard, refresh, logout, introspect."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request

from identity.api.deps import (
    get_audit_service,
    get_authn_service,
    get_billing_service,
    get_captcha_store,
    get_current_user,
    get_mfa_challenge_store,
    get_mfa_service,
    get_rate_limiter,
    get_token_service,
    get_user_repo,
)
from identity.core.client_ip import client_ip
from identity.core.config import Environment, settings
from identity.core.constants import (
    LOGIN_FAILED_MESSAGE,
    SIGNUP_CAPTCHA_LIMIT_KEY,
    SIGNUP_CHECK_LIMIT_KEY,
    SIGNUP_CODE_IP_LIMIT_KEY,
    SIGNUP_CODE_LIMIT_KEY,
    SIGNUP_START_LIMIT_KEY,
    SIGNUP_VERIFY_LIMIT_KEY,
)
from identity.core.user_agent import CLIENT_HINT_HEADERS
from identity.features.auth.captcha.captcha import generate_captcha, png_data_uri
from identity.features.auth.captcha.captcha_store import CaptchaStore
from identity.features.auth.schemas import (
    AuthResponse,
    CaptchaResponse,
    CheckEmailRequest,
    CheckEmailResponse,
    CheckSlugRequest,
    CheckSlugResponse,
    CreateOrganizationRequest,
    CreateOrganizationResponse,
    LoginRequest,
    LogoutRequest,
    MfaChallengeVerifyRequest,
    SendCodeRequest,
    SendCodeResponse,
    SetPasswordRequest,
    SetPasswordResponse,
    SignupCheckoutSessionRequest,
    SignupStartRequest,
    SignupStartResponse,
    TokenRefreshRequest,
    VerifyCodeRequest,
    VerifyCodeResponse,
)
from identity.features.auth.service import AuthenticationService, TokenService
from identity.features.billing.schemas import CheckoutSessionResponse
from identity.features.billing.service import BillingService
from skyrict_common.exceptions import AuthenticationError
from skyrict_common.schemas import ResponseEnvelope

if TYPE_CHECKING:
    from identity.core.rate_limit import RateLimiter
    from identity.features.audit.service import AuditService
    from identity.features.auth.mfa_challenge_store import MfaChallengeStore
    from identity.features.mfa.service import MFAService
    from identity.features.users.repository import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_hints(request: Request) -> dict[str, str]:
    """Collect the ``Sec-CH-UA*`` Client Hints headers sent by the browser."""
    return {
        name: request.headers[name] for name in CLIENT_HINT_HEADERS if request.headers.get(name)
    }


@router.post("/login", response_model=ResponseEnvelope[AuthResponse])
async def login(
    body: LoginRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ResponseEnvelope[AuthResponse]:
    """Authenticate a user and return tokens.

    Rate-limited per (source IP, account) - ``RATE_LIMIT_LOGIN`` attempts per
    ``RATE_LIMIT_WINDOW_SECONDS`` - to blunt brute-force and credential-
    stuffing against the highest-value endpoint. The limiter fails open when
    Redis is unavailable so a Redis outage never becomes a login outage.
    """
    ip_address = client_ip(request)
    await limiter.enforce(
        key=f"login:{ip_address}:{body.email.lower()}",
        limit=settings.RATE_LIMIT_LOGIN,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )

    await limiter.enforce(
        key=f"login-ip:{ip_address}",
        limit=settings.RATE_LIMIT_LOGIN_IP,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )

    result = await authn.login(
        body,
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
        client_hints=_client_hints(request),
    )
    user = result.pop("user")
    return ResponseEnvelope(
        data=AuthResponse(**result, user=user),
        message="Login successful",
    )


@router.post("/mfa/verify", response_model=ResponseEnvelope[AuthResponse])
async def verify_mfa_challenge(
    body: MfaChallengeVerifyRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
    mfa_service: MFAService = Depends(get_mfa_service),
    user_repo: UserRepository = Depends(get_user_repo),
    audit_service: AuditService = Depends(get_audit_service),
    challenge_store: MfaChallengeStore = Depends(get_mfa_challenge_store),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ResponseEnvelope[AuthResponse]:
    """Redeem a login mfaToken with a TOTP/backup code and issue the token pair."""

    ip_address = client_ip(request)
    await limiter.enforce(
        key=f"mfa-verify-ip:{ip_address}",
        limit=settings.RATE_LIMIT_MFA_VERIFY,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    await limiter.enforce(
        key=f"mfa-verify-token:{body.mfa_token}",
        limit=settings.RATE_LIMIT_MFA_VERIFY,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )

    challenge = await challenge_store.get(body.mfa_token)
    if challenge is None:
        raise AuthenticationError(LOGIN_FAILED_MESSAGE)

    attempts = await challenge_store.increment_attempts(body.mfa_token)
    if attempts > settings.MFA_CHALLENGE_MAX_ATTEMPTS:
        await challenge_store.consume(body.mfa_token)
        raise AuthenticationError(LOGIN_FAILED_MESSAGE)

    user = await user_repo.get_by_id(uuid.UUID(challenge["user_id"]))
    if user is None or not user.is_active or not user.is_verified:
        await challenge_store.consume(body.mfa_token)
        raise AuthenticationError(LOGIN_FAILED_MESSAGE)

    assert user.id is not None

    verified = await mfa_service.verify_totp(user.id, body.code)
    if not verified:
        verified = await mfa_service.redeem_backup_code(user.id, body.code)
    if not verified:
        await audit_service.log(
            action="auth.login.mfa.verify_failed",
            target=f"user:{user.id}",
            user_id=str(user.id),
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent"),
            tenant_id=challenge["tenant_id"],
        )
        raise AuthenticationError(LOGIN_FAILED_MESSAGE)

    await challenge_store.consume(body.mfa_token)
    result = await authn.complete_authenticated_login(
        user=user,
        tenant_id=challenge["tenant_id"],
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
        client_hints=_client_hints(request),
        audit_action="auth.login.mfa_verified",
    )
    user_response = result.pop("user")
    return ResponseEnvelope(
        data=AuthResponse(**result, user=user_response),
        message="MFA verified",
    )


@router.post("/signup/start", response_model=ResponseEnvelope[SignupStartResponse])
async def signup_start(
    body: SignupStartRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ResponseEnvelope[SignupStartResponse]:
    """Gate the wizard: server-side Turnstile verification + per-IP throttling."""
    ip_address = client_ip(request)
    await limiter.enforce(
        key=f"{SIGNUP_START_LIMIT_KEY}:{ip_address}",
        limit=settings.SIGNUP_START_RATE_LIMIT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    result = await authn.signup_start(email=body.email, turnstile_token=body.turnstile_token)
    return ResponseEnvelope(data=SignupStartResponse(**result))


@router.post("/signup/send-code", response_model=ResponseEnvelope[SendCodeResponse])
async def signup_send_code(
    body: SendCodeRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ResponseEnvelope[SendCodeResponse]:
    """Send a 6-digit OTP to the address (proof-gated, throttled per email and per IP).

    This endpoint is the one that actually sends mail, so it is gated - but on
    the flow proof minted by /signup/start rather than on a second challenge.
    The proof is issued only after a CAPTCHA passes and only for one address, so
    a caller who skipped or replayed the wizard still cannot mint OTPs for
    arbitrary addresses or spend relay quota on them. Asking the user to solve a
    second challenge seconds later bought nothing this does not already hold,
    and cost them a step they could fail on a request already proven.
    """
    ip_address = client_ip(request)
    email_key = body.email.lower()
    await limiter.enforce(
        key=f"{SIGNUP_CODE_LIMIT_KEY}:{email_key}",
        limit=settings.SIGNUP_CODE_RATE_LIMIT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    await limiter.enforce(
        key=f"{SIGNUP_CODE_IP_LIMIT_KEY}:{ip_address}",
        limit=settings.SIGNUP_CODE_RATE_LIMIT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    result = await authn.signup_send_code(email=body.email, flow_token=body.flow_token)
    return ResponseEnvelope(data=SendCodeResponse(**result))


@router.post("/signup/verify-code", response_model=ResponseEnvelope[VerifyCodeResponse])
async def signup_verify_code(
    body: VerifyCodeRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ResponseEnvelope[VerifyCodeResponse]:
    """Check an OTP; on success return an opaque single-use verification token."""
    await limiter.enforce(
        key=f"{SIGNUP_VERIFY_LIMIT_KEY}:{body.email.lower()}",
        limit=settings.SIGNUP_VERIFY_RATE_LIMIT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    result = await authn.signup_verify_code(email=body.email, code=body.code)
    return ResponseEnvelope(data=VerifyCodeResponse(**result))


@router.get("/signup/captcha", response_model=ResponseEnvelope[CaptchaResponse])
async def signup_captcha(
    request: Request,
    captcha_store: CaptchaStore = Depends(get_captcha_store),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ResponseEnvelope[CaptchaResponse]:
    """Issue a text CAPTCHA challenge for the password step (rate-limited per IP)."""
    ip_address = client_ip(request)
    await limiter.enforce(
        key=f"{SIGNUP_CAPTCHA_LIMIT_KEY}:{ip_address}",
        limit=settings.SIGNUP_CAPTCHA_RATE_LIMIT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    captcha = generate_captcha()
    captcha_id = await captcha_store.issue(captcha.text)
    return ResponseEnvelope(
        data=CaptchaResponse(
            captcha_id=captcha_id,
            image=png_data_uri(captcha.image_png),
            expires_in=settings.CAPTCHA_TTL_SECONDS,
            # Plaintext answer only in TEST so integration tests can drive the
            # wizard; everywhere else the user reads the code from the image.
            answer=captcha.text if settings.ENVIRONMENT == Environment.TEST else None,
        )
    )


@router.post("/signup/password", response_model=ResponseEnvelope[SetPasswordResponse])
async def signup_password(
    body: SetPasswordRequest,
    authn: AuthenticationService = Depends(get_authn_service),
) -> ResponseEnvelope[SetPasswordResponse]:
    """Set the password for the wizard session bound to the verification token."""
    result = await authn.signup_set_password(
        email=body.email,
        verification_token=body.verification_token,
        password=body.password,
        captcha_id=body.captcha_id,
        captcha_answer=body.captcha_answer,
    )
    return ResponseEnvelope(data=SetPasswordResponse(**result))


@router.post("/signup/check-email", response_model=ResponseEnvelope[CheckEmailResponse])
async def signup_check_email(
    body: CheckEmailRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ResponseEnvelope[CheckEmailResponse]:
    """Expose email availability for the account step (rate-limited per IP)."""
    ip_address = client_ip(request)
    await limiter.enforce(
        key=f"{SIGNUP_CHECK_LIMIT_KEY}:{ip_address}",
        limit=settings.SIGNUP_CHECK_RATE_LIMIT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    result = await authn.signup_check_email(email=body.email)
    return ResponseEnvelope(data=CheckEmailResponse(**result))


@router.post("/signup/check-slug", response_model=ResponseEnvelope[CheckSlugResponse])
async def signup_check_slug(
    body: CheckSlugRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ResponseEnvelope[CheckSlugResponse]:
    """Expose workspace slug availability for the organization step."""
    ip_address = client_ip(request)
    await limiter.enforce(
        key=f"{SIGNUP_CHECK_LIMIT_KEY}:{ip_address}",
        limit=settings.SIGNUP_CHECK_RATE_LIMIT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    result = await authn.signup_check_slug(slug=body.slug)
    return ResponseEnvelope(data=CheckSlugResponse(**result))


@router.post("/signup/organization", response_model=ResponseEnvelope[CreateOrganizationResponse])
async def signup_organization(
    body: CreateOrganizationRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
) -> ResponseEnvelope[CreateOrganizationResponse]:
    """Provision the tenant, roles, and verified owner in one transaction."""
    result = await authn.signup_create_organization(
        body,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ResponseEnvelope(
        data=CreateOrganizationResponse(**result),
        message="Your organization is ready",
    )


@router.post("/signup/checkout-session", response_model=ResponseEnvelope[CheckoutSessionResponse])
async def signup_checkout_session(
    body: SignupCheckoutSessionRequest,
    authn: AuthenticationService = Depends(get_authn_service),
    billing_svc: BillingService = Depends(get_billing_service),
) -> ResponseEnvelope[CheckoutSessionResponse]:
    """Create a Stripe Checkout session for a plan picked mid-onboarding.

    The wizard's Plan/Billing steps run before the owner has an account, so
    this endpoint is guarded by the verification token rather than a session:
    the caller must still hold the token bound to the owner email AND the
    email must own a user inside the tenant (see
    ``AuthenticationService.resolve_signup_checkout_tenant``). Returns the
    Stripe-hosted ``url`` the browser redirects to; Stripe sends the owner
    back to the signup Review step on success. Bad token/tenant -> 401,
    plan without a configured Price -> 422, Stripe disabled -> sanitized 503.
    """
    tenant = await authn.resolve_signup_checkout_tenant(
        email=body.email,
        verification_token=body.verification_token,
        tenant_id=body.tenant_id,
    )
    assert tenant.id is not None  # resolved tenant is persisted
    session = await billing_svc.create_signup_checkout_session(
        tenant_id=str(tenant.id),
        plan_id=body.plan_id,
        interval=body.interval,
        currency=body.currency,
    )
    return ResponseEnvelope(data=CheckoutSessionResponse.model_validate(session))


@router.post("/refresh", response_model=ResponseEnvelope[AuthResponse])
async def refresh_token(
    body: TokenRefreshRequest,
    token_svc: TokenService = Depends(get_token_service),
) -> ResponseEnvelope[AuthResponse]:
    """Refresh an access token using a refresh token."""
    tokens = await token_svc.refresh_tokens(body.refresh_token)
    return ResponseEnvelope(
        data=AuthResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
        ),
        message="Token refreshed",
    )


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    token_svc: TokenService = Depends(get_token_service),
) -> ResponseEnvelope[None]:
    """Revoke the current session."""
    if body.refresh_token:
        await token_svc.revoke_token(body.refresh_token)
    return ResponseEnvelope(message="Logged out successfully")


@router.post("/introspect")
async def introspect_token(
    body: TokenRefreshRequest,
    token_svc: TokenService = Depends(get_token_service),
) -> ResponseEnvelope[dict[str, Any]]:
    """Introspect a token - return its claims if active."""
    result = await token_svc.introspect(body.refresh_token)
    return ResponseEnvelope(data=result)
