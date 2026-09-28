"""Application-wide constants - single source of truth for magic values.

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

# NOTE: RFC 7807 problem types are NOT defined here. They used to be - a
# PROBLEM_BASE_URL literal plus 21 derived PROBLEM_* constants, none of which
# anything outside this file ever read, alongside a second, live copy in
# core/exceptions.py. Two definitions of one published contract is how the base
# drifted to a retired domain (pre-release audit finding 16). The base now lives
# in skyrict_common.problems, and core/exceptions.py is the only consumer.

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
# Everything else - including /api/v1/auth/login - requires tenant resolution
# so the tenant is known before route execution. The onboarding wizard paths
# (/auth/signup/*) and /invitations/accept|verify are self-service (no tenant
# exists yet), so they bypass tenant resolution. The Stripe webhook bypasses it
# too: Stripe authenticates via its own signature over the raw body, and no
# tenant context exists for a pre-checkout event. The public signup plan
# catalog serves the pre-login wizard Plan step; the signup checkout-session
# endpoint is guarded by the wizard verification token instead of a session.
# ---------------------------------------------------------------------------
SKIP_AUTH_PATHS = frozenset(
    {
        f"{API_V1_PREFIX}/health",
        f"{API_V1_PREFIX}/ready",
        f"{API_V1_PREFIX}/billing/webhooks",
        f"{API_V1_PREFIX}/billing/signup/plans",
        f"{API_V1_PREFIX}/auth/signup/start",
        f"{API_V1_PREFIX}/auth/signup/send-code",
        f"{API_V1_PREFIX}/auth/signup/verify-code",
        f"{API_V1_PREFIX}/auth/signup/password",
        f"{API_V1_PREFIX}/auth/signup/captcha",
        f"{API_V1_PREFIX}/auth/signup/check-email",
        f"{API_V1_PREFIX}/auth/signup/check-slug",
        f"{API_V1_PREFIX}/auth/signup/organization",
        f"{API_V1_PREFIX}/auth/signup/checkout-session",
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
            "erp.inventory.adjust",
            "erp.inventory.adjust.approve",
            "erp.inventory.cost",
            "erp.inventory.suppliers.read",
            "erp.inventory.suppliers.write",
            "erp.finance.read",
            "erp.finance.write",
            "erp.finance.approve",
            "erp.hr.read",
            "erp.hr.write",
            "erp.hr.approve",
            "erp.hr.ai.eval",
            "erp.hr.ai.management",
            "erp.payroll.read",
            "erp.payroll.write",
            "erp.payroll.approve",
            "erp.payroll.ai.read",
            "erp.payroll.ai.run",
            "erp.payroll.ai.notify",
            "erp.payroll.ai.approve",
            "erp.ai.invoke",
            "erp.ai.narrator.refresh",
            "erp.ai.l3.refresh",
            "erp.ai.coaching.read",
            "erp.ai.coaching.review",
            "erp.ai.guardian.read",
            "erp.ai.guardian.review",
            "erp.reports.read",
            "erp.reports.create",
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
            "erp.reports.read",
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
            "erp.payroll.ai.read",
            "erp.reports.read",
        ),
    ),
    # Employee self-service: portal access to OWN leave balances/requests only.
    # Deliberately holds zero dashboard permissions - the login redirect sends
    # sole holders straight to the /leave portal.
    ("employee_self_service", ("erp.leave.self",)),
)

SYSTEM_ROLE_NAMES = frozenset(name for name, _ in SYSTEM_ROLE_DEFINITIONS)

# The tenant ownership role. Permission resolution
# (``RoleRepository.get_permissions_for_user``) treats whoever holds it as
# having full access regardless of the stored permission array, so an owner can
# never silently lose permissions through drift or a historical bad update.
TENANT_OWNER_ROLE = "tenant_owner"

INVITATION_TOKEN_EXPIRE_DAYS = 7
# Employee-portal invites are shorter-lived (spec: single-use, 72h).
EMPLOYEE_INVITE_TOKEN_EXPIRE_HOURS = 72
DEFAULT_INVITE_ROLE = "standard_user"
