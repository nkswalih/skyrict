"""Authentication schemas - requests, responses, and token payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasGenerator, BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel

from identity.features.billing.plans import CURRENCY_LITERAL
from identity.features.users.schemas import UserResponse


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(validation_alias=to_camel, serialization_alias=to_camel),
    )


class LoginRequest(BaseModel):
    """POST /auth/login"""

    email: EmailStr
    password: str = Field(..., min_length=1)
    tenant_slug: str | None = Field(default=None, description="Tenant slug for multi-tenant login")


class TokenRefreshRequest(BaseModel):
    """POST /auth/refresh"""

    refresh_token: str


class LogoutRequest(BaseModel):
    """POST /auth/logout"""

    refresh_token: str | None = Field(
        default=None, description="Specific token to revoke; if omitted, revoke all"
    )


class TokenPayloadSchema(BaseModel):
    """Decoded JWT payload."""

    sub: str
    tenant_id: str
    type: str  # "access" or "refresh"
    exp: int
    iat: int


class TokenIntrospectionResponse(BaseModel):
    """POST /auth/introspect - token introspection."""

    active: bool
    sub: str | None = None
    tenant_id: str | None = None
    type: str | None = None
    exp: int | None = None
    scope: str | None = None


class AuthResponse(BaseModel):
    """Response after successful login/refresh."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int = Field(default=900, description="Access token TTL in seconds")
    mfa_required: bool = Field(
        default=False,
        description="True when MFA must be satisfied before tokens are usable",
    )
    mfa_token: str | None = Field(
        default=None,
        description='Single-use challenge token when next_step is "mfa.verify"',
    )
    next_step: str | None = Field(
        default=None,
        description='Required next step when mfa_required - "mfa.setup" or "mfa.verify"',
    )
    user: UserResponse | None = None


class MfaChallengeVerifyRequest(BaseModel):
    """POST /auth/mfa/verify request body."""

    code: str = Field(..., min_length=6, max_length=32, description="TOTP code or backup code")
    mfa_token: str = Field(..., description="Opaque challenge token from the login response")


# ---------------------------------------------------------------------------
# Onboarding wizard schemas (SKY-30).
#
# The wizard is the web app's contract: its TypeScript client speaks camelCase
# (verificationToken, planId, ...), so these models alias snake_case Python
# fields to camelCase JSON while keeping idiomatic names in service code.
# ---------------------------------------------------------------------------


class SignupStartRequest(_CamelModel):
    """POST /auth/signup/start"""

    email: EmailStr
    turnstile_token: str | None = Field(default=None, description="Cloudflare Turnstile response")


class SignupStartResponse(_CamelModel):
    """Response after a successful Turnstile + email gate.

    ``flow_token`` is the proof the rest of the wizard spends. It replaces a
    second CAPTCHA challenge on the code request: one solve per signup, then a
    short-lived, email-bound token carries the flow forward.
    """

    status: Literal["ok"] = "ok"
    flow_token: str = Field(
        description="Short-lived proof that the challenge was cleared for this address"
    )


class SendCodeRequest(_CamelModel):
    """POST /auth/signup/send-code"""

    email: EmailStr
    flow_token: str | None = Field(
        default=None,
        description=(
            "Proof from /signup/start. Required: this endpoint mints and sends an "
            "email, so a caller that never cleared the wizard's challenge must not "
            "be able to burn relay quota on addresses they do not own."
        ),
    )


class SendCodeResponse(_CamelModel):
    """
    Response after an OTP is sent (or a resend is still cooling down).

    ``code`` is exposed only outside production (dev/test).
    """

    status: Literal["ok"] = "ok"
    resend_in: int = Field(default=60, description="Seconds until a new code can be sent")
    code: str | None = Field(default=None, description="Plaintext OTP, dev/test only")


class VerifyCodeRequest(_CamelModel):
    """POST /auth/signup/verify-code"""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class VerifyCodeResponse(_CamelModel):
    """Result of an OTP check - never reveals whether the email has an account."""

    status: Literal["ok", "invalid", "expired"]
    verification_token: str | None = Field(default=None, description="Opaque single-use token")


class SetPasswordRequest(_CamelModel):
    """POST /auth/signup/password"""

    email: EmailStr
    verification_token: str
    password: str = Field(..., min_length=12)
    captcha_id: str = Field(..., min_length=1, max_length=64, description="Opaque challenge id")
    captcha_answer: str = Field(..., min_length=1, max_length=16)


class SetPasswordResponse(_CamelModel):
    """Response after the wizard password is set."""

    status: Literal["ok"] = "ok"


class CaptchaResponse(_CamelModel):
    """GET /auth/signup/captcha - a text CAPTCHA challenge.

    ``answer`` is the plaintext code exposed ONLY in test so integration
    tests can drive the wizard; every other environment returns ``None`` and
    the user reads the code from the image.
    """

    captcha_id: str
    image: str = Field(description="base64 PNG data URI of the rendered challenge")
    expires_in: int = Field(description="TTL of the challenge in seconds")
    answer: str | None = Field(default=None, description="Plaintext answer, test only")


class CheckEmailRequest(_CamelModel):
    """POST /auth/signup/check-email"""

    email: EmailStr


class CheckEmailResponse(_CamelModel):
    """Availability of an email for self-service signup."""

    available: bool


class CheckSlugRequest(_CamelModel):
    """POST /auth/signup/check-slug"""

    slug: str = Field(..., min_length=1, max_length=100)


class CheckSlugResponse(_CamelModel):
    """Availability of a workspace slug."""

    available: bool


class BillingAddress(_CamelModel):
    """Billing address captured on the organization step."""

    country: str = Field(..., min_length=2, max_length=2)
    address_line1: str = Field(..., min_length=1, max_length=256)
    address_line2: str | None = Field(default=None, max_length=256)
    city: str = Field(..., min_length=1, max_length=120)
    state: str = Field(..., min_length=1, max_length=120)
    postal_code: str = Field(..., min_length=1, max_length=24)


class CreateOrganizationRequest(_CamelModel):
    """POST /auth/signup/organization - provisions the tenant.

    The tenant is created on the Organization step (before the Plan step).
    ``plan_id`` defaults to ``starter`` because the plan is not known yet -
    the wizard picks a plan AFTER the tenant exists and a checkout happens on
    the Billing step. The backend never creates the tenant without a tier.
    """

    email: EmailStr
    verification_token: str
    plan_id: Literal["starter", "professional", "business", "enterprise"] = Field(
        default="starter", description="Selected plan (defaults to Starter before the Plan step)"
    )
    company_name: str = Field(..., min_length=1, max_length=256)
    industry: str = Field(..., min_length=1, max_length=120)
    workspace_slug: str = Field(..., min_length=1, max_length=100)
    owner_full_name: str = Field(..., min_length=1, max_length=256)
    phone_country: str | None = Field(default=None, max_length=4)
    phone_number: str | None = Field(default=None, max_length=24)
    address: BillingAddress | None = None


class CreateOrganizationResponse(_CamelModel):
    """Response after the organization is provisioned - MFA setup is mandatory."""

    status: Literal["ok"] = "ok"
    mfa_required: bool = True
    tenant_id: UUID
    tenant_slug: str
    subscription_status: Literal["trialing"] = "trialing"
    trial_ends_at: datetime | None = None


class SignupCheckoutSessionRequest(_CamelModel):
    """POST /auth/signup/checkout-session - create a Checkout session mid-wizard.

    The wizard's Plan/Billing steps run BEFORE the owner has an account (the
    tenant was provisioned on the Organization step). This request carries the
    same verification token bound to the owner email at the verify-code step -
    the token is the credential, so the endpoint is deliberately skipped by
    the auth middleware. Stripe redirects the owner back to the signup Review
    step when the checkout completes.
    """

    email: EmailStr
    verification_token: str
    tenant_id: UUID
    plan_id: Literal["starter", "professional", "business", "enterprise"]
    interval: Literal["month", "year"] = Field(
        default="month", description="Billing interval (monthly or annual)"
    )
    currency: CURRENCY_LITERAL = Field(
        default="usd",
        description=(
            "Currency for the billed price (beta allowlist). Selects a "
            "currency-specific Stripe Price; pricing-pending markets are "
            "rejected by the service layer."
        ),
    )
