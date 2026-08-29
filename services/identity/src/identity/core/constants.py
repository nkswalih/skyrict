"""Application-wide constants — single source of truth for magic values.

Services, schemas, and configs import from here instead of hardcoding strings.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# JWT / Token constants
# ---------------------------------------------------------------------------
ALGORITHM_RS256 = "RS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------
API_V1_PREFIX = "/api/v1"
SERVICE_NAME = "identity"
SERVICE_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Problem type URIs (RFC 7807)
# ---------------------------------------------------------------------------
PROBLEM_BASE_URL = "https://api.skyrict.io/problems"

PROBLEM_TOKEN_EXPIRED = f"{PROBLEM_BASE_URL}/token-expired"
PROBLEM_TOKEN_INVALID = f"{PROBLEM_BASE_URL}/token-invalid"
PROBLEM_TOKEN_REUSE_DETECTED = f"{PROBLEM_BASE_URL}/token-reuse-detected"
PROBLEM_AUTHENTICATION_ERROR = f"{PROBLEM_BASE_URL}/authentication-error"
PROBLEM_EMAIL_NOT_VERIFIED = f"{PROBLEM_BASE_URL}/email-not-verified"
PROBLEM_AUTHORIZATION_ERROR = f"{PROBLEM_BASE_URL}/authorization-error"
PROBLEM_MFA_REQUIRED = f"{PROBLEM_BASE_URL}/mfa-required"
PROBLEM_USER_NOT_FOUND = f"{PROBLEM_BASE_URL}/user-not-found"
PROBLEM_TENANT_NOT_FOUND = f"{PROBLEM_BASE_URL}/tenant-not-found"
PROBLEM_USER_ALREADY_EXISTS = f"{PROBLEM_BASE_URL}/user-already-exists"
PROBLEM_VALIDATION_ERROR = f"{PROBLEM_BASE_URL}/validation-error"
PROBLEM_RATE_LIMIT_EXCEEDED = f"{PROBLEM_BASE_URL}/rate-limit-exceeded"
PROBLEM_TENANT_DISABLED = f"{PROBLEM_BASE_URL}/tenant-disabled"
PROBLEM_USER_DISABLED = f"{PROBLEM_BASE_URL}/user-disabled"
PROBLEM_TENANT_CONTEXT_MISSING = f"{PROBLEM_BASE_URL}/tenant-context-missing"
PROBLEM_TENANT_MISMATCH = f"{PROBLEM_BASE_URL}/tenant-mismatch"
PROBLEM_INTERNAL_ERROR = f"{PROBLEM_BASE_URL}/internal-error"

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 15
DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS = 7
DEFAULT_TOKEN_EXPIRE_SECONDS = 900
DEFAULT_PAGE_SIZE = 20
DEFAULT_RATE_LIMIT_LOGIN = 5
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 300

# ---------------------------------------------------------------------------
# Login security posture (see ADR-004)
#
# One message for EVERY login failure (unknown email, wrong password,
# disabled, unverified) so the API exposes no account-existence oracle via
# status code, problem type, or detail. The frontend guides recovery via
# account-level state (SKY-21), never via backend error semantics.
# ---------------------------------------------------------------------------
LOGIN_FAILED_MESSAGE = "Invalid email or password."

# ---------------------------------------------------------------------------
# Skip-auth paths (middleware bypass)
#
# These are the REAL mounted paths (the api_router is mounted under /api/v1).
# Everything else — including /api/v1/auth/login — requires tenant resolution
# so the tenant is known before route execution. The onboarding wizard paths
# (/auth/signup/*) and /invitations/accept|verify are self-service (no tenant
# exists yet), so they bypass tenant resolution.
# ---------------------------------------------------------------------------
SKIP_AUTH_PATHS = frozenset(
    {
        f"{API_V1_PREFIX}/health",
        f"{API_V1_PREFIX}/ready",
        f"{API_V1_PREFIX}/auth/signup/start",
        f"{API_V1_PREFIX}/auth/signup/send-code",
        f"{API_V1_PREFIX}/auth/signup/verify-code",
        f"{API_V1_PREFIX}/auth/signup/password",
        f"{API_V1_PREFIX}/auth/signup/captcha",
        f"{API_V1_PREFIX}/auth/signup/check-email",
        f"{API_V1_PREFIX}/auth/signup/check-slug",
        f"{API_V1_PREFIX}/auth/signup/organization",
        f"{API_V1_PREFIX}/invitations/accept",
        f"{API_V1_PREFIX}/invitations/verify",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)

# ---------------------------------------------------------------------------
# Onboarding wizard
#
# Platform-owned workspace slugs and email addresses are never available for
# self-service. The check-email / check-slug endpoints treat them as taken.
#
# The set covers every platform hostname that must never be a tenant
# subdomain: marketing (web, www), auth surfaces (signup, signin, app, auth,
# login), API/infra (api, docs, status, mail, support, help, blog), tooling
# (dev, test, staging), the placeholder demo tenant (acme), and the apex brand
# (skyrict). The tenant resolver returns None for these so platform hosts are
# never looked up as tenants.
# ---------------------------------------------------------------------------
RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "app",
        "blog",
        "docs",
        "dev",
        "help",
        "mail",
        "signin",
        "signup",
        "staging",
        "status",
        "support",
        "test",
        "web",
        "www",
        "acme",
        "skyrict",
    }
)
RESERVED_EMAILS = frozenset(
    {
        "admin@skyrict.com",
        "no-reply@skyrict.com",
        "sales@skyrict.com",
        "support@skyrict.com",
    }
)

SIGNUP_START_LIMIT_KEY = "signup_start_ip"
SIGNUP_CODE_LIMIT_KEY = "signup_code"
SIGNUP_CODE_IP_LIMIT_KEY = "signup_code_ip"
SIGNUP_VERIFY_LIMIT_KEY = "signup_verify"
SIGNUP_CHECK_LIMIT_KEY = "signup_check_ip"
SIGNUP_CAPTCHA_LIMIT_KEY = "signup_captcha_ip"

# ---------------------------------------------------------------------------
# Default system roles (single source of truth)
#
# Provisioned for every tenant at self-service registration and seeded for the
# default tenant. Permission keys must come from the platform-fixed catalog
# seeded by the 0001 migration (``PERMISSION_CATALOG``). Kept in core so the
# auth feature (provisioning), the roles feature (validation), and seed tooling
# can all import it without crossing feature boundaries.
# ---------------------------------------------------------------------------
SYSTEM_ROLE_DEFINITIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tenant_owner", ("*", "invitations:send")),
    (
        "organization_admin",
        (
            "users:read",
            "users:write",
            "users:delete",
            "roles:read",
            "roles:write",
            "tenants:read",
            "tenants:write",
            "sessions:read",
            "sessions:revoke",
            "audit:read",
            "mfa:manage",
            "sso:manage",
            "settings:read",
            "settings:write",
            "erp.invoice.read",
            "erp.invoice.approve",
            "erp.purchase.approve",
            "erp.crm.read",
            "erp.crm.write",
            "erp.sales.read",
            "erp.sales.write",
            "erp.sales.approve",
            "erp.inventory.read",
            "erp.inventory.write",
            "erp.inventory.approve",
            "erp.inventory.ai.approve",
            "erp.finance.read",
            "erp.finance.write",
            "erp.hr.read",
            "erp.hr.write",
            "erp.hr.approve",
            "erp.payroll.read",
            "erp.payroll.write",
            "erp.payroll.approve",
            "erp.ai.invoke",
            "agents:read",
            "intelligence:read",
            "billing.manage",
            "invitations:send",
        ),
    ),
    (
        "department_manager",
        (
            "users:read",
            "roles:read",
            "settings:read",
            "sessions:read",
            "erp.invoice.read",
            "erp.crm.read",
            "erp.crm.write",
            "erp.sales.read",
            "erp.sales.write",
            "erp.inventory.read",
            "erp.inventory.write",
            "erp.inventory.ai.approve",
            "erp.finance.read",
            "erp.finance.write",
            "erp.hr.read",
            "erp.hr.write",
            "erp.payroll.read",
        ),
    ),
    (
        "standard_user",
        (
            "users:read",
            "settings:read",
            "erp.invoice.read",
            "erp.crm.read",
            "erp.sales.read",
            "erp.inventory.read",
            "erp.finance.read",
            "erp.hr.read",
        ),
    ),
    (
        "auditor",
        (
            "audit:read",
            "sessions:read",
            "users:read",
            "roles:read",
            "erp.invoice.read",
            "erp.crm.read",
            "erp.sales.read",
            "erp.inventory.read",
            "erp.finance.read",
            "erp.hr.read",
            "erp.payroll.read",
        ),
    ),
    # Employee self-service: portal access to OWN leave balances/requests only.
    # Deliberately holds zero dashboard permissions — the login redirect sends
    # sole holders straight to the /leave portal.
    ("employee_self_service", ("erp.leave.self",)),
)

SYSTEM_ROLE_NAMES = frozenset(name for name, _ in SYSTEM_ROLE_DEFINITIONS)

INVITATION_TOKEN_EXPIRE_DAYS = 7
# Employee-portal invites are shorter-lived (spec: single-use, 72h).
EMPLOYEE_INVITE_TOKEN_EXPIRE_HOURS = 72
DEFAULT_INVITE_ROLE = "standard_user"

PROBLEM_INVITATION_NOT_FOUND = f"{PROBLEM_BASE_URL}/invitation-not-found"
PROBLEM_INVITATION_EXPIRED = f"{PROBLEM_BASE_URL}/invitation-expired"
PROBLEM_INVITATION_ALREADY_USED = f"{PROBLEM_BASE_URL}/invitation-already-used"
PROBLEM_INVITATION_EMAIL_MISMATCH = f"{PROBLEM_BASE_URL}/invitation-email-mismatch"
