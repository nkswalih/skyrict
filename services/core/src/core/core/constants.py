"""Application-wide constants - single source of truth for magic values."""

from __future__ import annotations

import enum

# ---------------------------------------------------------------------------
# HR & Payroll domain enums
#
# The ORM models define their own native StrEnums (backing the Postgres enum
# types created by migration 0005). These domain copies are the values the
# service layer reasons about - identical string values, so repository mapping
# between entity.status (here) and model.status (models) is value-safe. Shared
# via constants.py per the HR/Payroll spec §2.1 ("enums, problem URIs,
# defaults").
# ---------------------------------------------------------------------------


class EmploymentStatus(enum.StrEnum):
    """Employment lifecycle - mirrors ``erp_employment_status``."""

    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"


class LeaveRequestStatus(enum.StrEnum):
    """Leave request lifecycle - mirrors ``erp_leave_request_status``."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PayrollRunStatus(enum.StrEnum):
    """Payroll run lifecycle - mirrors ``erp_payroll_run_status``."""

    DRAFT = "draft"
    COMPUTED = "computed"
    APPROVED = "approved"
    PAID = "paid"
    VOID = "void"


class PayrollJeBridgeStatus(enum.StrEnum):
    """Payroll→Finance accrual journal-entry bridge state (HR-AUT-001, Commit 4).

    Mirrors ``erp_payroll_runs.je_bridge_status`` (a String column + CHECK, not
    a native enum, so FIN-AI-001 can extend it without a migration).

    ``none``
        The bridge never ran or has nothing to book (bridge disabled on the
        tenant, run not paid, zero-dollar run, or run voided).
    ``pending``
        The run is paid but no accrual JE was created — the tenant's chart of
        accounts is missing one of the payroll account codes (5010/2010/2020),
        i.e. the same per-tenant chart gap flagged in the finance backlog
        (docs/backlog/finance-chart-of-accounts-gap.md). Queryable and
        retryable: provision the chart, then re-run the bridge.
    ``draft``
        A DRAFT accrual journal entry (source='payroll', source_ref=run id) now
        sits in the Finance inbox; it is posted/voided through the existing
        finance endpoints (FIN-AI-001 consumes this seam later).
    """

    NONE = "none"
    PENDING = "pending"
    DRAFT = "draft"


class PayrollRounding(enum.StrEnum):
    """Net rounding mode - mirrors ``erp_payroll_rounding``."""

    NEAREST = "nearest"
    UP = "up"
    DOWN = "down"


class AttendanceStatus(enum.StrEnum):
    """Daily attendance outcome - mirrors ``erp_attendance_status``."""

    ON_TIME = "on_time"
    LATE = "late"
    ABSENT = "absent"


class PayImpact(enum.StrEnum):
    """Payroll impact derived from attendance status.

    ``on_time`` -> full pay, ``late`` -> half pay, ``absent`` -> no pay for
    the day. Derived by the service, stored on the row.
    """

    FULL = "full"
    HALF = "half"
    NONE = "none"


# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------
API_V1_PREFIX = "/api/v1"
SERVICE_NAME = "core"
SERVICE_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# JWT constants
# ---------------------------------------------------------------------------
ALGORITHM_RS256 = "RS256"
TOKEN_TYPE_ACCESS = "access"

# NOTE: RFC 7807 problem types are NOT defined here. They used to be - a
# PROBLEM_BASE_URL literal plus 12 derived PROBLEM_* constants, none of which
# anything outside this file ever read, alongside a second, live copy in
# core/exceptions.py. Two definitions of one published contract is how the base
# drifted to a retired domain (pre-release audit finding 16). The base now lives
# in skyrict_common.problems, and core/exceptions.py is the only consumer.

# ---------------------------------------------------------------------------
# Finance - document numbering
# ---------------------------------------------------------------------------
INVOICE_PREFIX = "INV"
PAYMENT_PREFIX = "PMT"

# ---------------------------------------------------------------------------
# Finance - standard account codes for auto-generated entries.
# Fixed platform defaults (user-editable COA entries still override at runtime).
# ---------------------------------------------------------------------------
AR_ACCOUNT_CODE = "1100"
CASH_ACCOUNT_CODE = "1200"
AP_ACCOUNT_CODE = "2110"
REVENUE_ACCOUNT_CODE = "4000"
COGS_ACCOUNT_CODE = "5000"
INVENTORY_ASSET_ACCOUNT_CODE = "1300"
# Payroll accrual codes (HR-AUT-001, Commit 4) — reuse the demo chart's codes,
# seeded per-tenant by the finance owner (see backlog gap doc). The bridge
# books DR Salaries Expense / CR Accrued Salaries / CR Deductions Payable.
SALARY_EXPENSE_ACCOUNT_CODE = "5010"
ACCRUED_SALARIES_PAYABLE_ACCOUNT_CODE = "2010"
DEDUCTIONS_PAYABLE_ACCOUNT_CODE = "2020"
# FIN-AUT-004 (SKY-85 B28): the depreciation run books
# DR Depreciation Expense / CR Accumulated Depreciation against these codes,
# seeded per-tenant in the demo chart (see backlog gap doc).
DEPRECIATION_EXPENSE_ACCOUNT_CODE = "5100"
ACCUMULATED_DEPRECIATION_ACCOUNT_CODE = "1700"

# ---------------------------------------------------------------------------
# Finance - journal entry and invoice provenance (idempotency source keys).
# ---------------------------------------------------------------------------
JOURNAL_SOURCE_MANUAL = "manual"
JOURNAL_SOURCE_INVOICE = "invoice"
JOURNAL_SOURCE_PAYMENT = "payment"
JOURNAL_SOURCE_COGS = "cogs"
JOURNAL_SOURCE_PAYROLL = "payroll"
# FIN-AUT-003 B5: recurring journal templates stamp their generated drafts with
# source='journal_template' + source_ref=f"{template_id}:{entry_date}" so the
# UNIQUE (tenant, source, source_ref) lock makes every scheduled occurrence
# generate exactly once.
JOURNAL_SOURCE_TEMPLATE = "journal_template"
# HR-AI-004 (SKY-93, Commit 4): idempotency source key for proposed budget
# drafts exported from the L4 what-if planner (erp_budget_drafts).
BUDGET_DRAFT_SOURCE_WORKFORCE_PLAN = "workforce_plan"
# FIN-AUT-004 (SKY-85): depreciation run stamps its DRAFT journal entries with
# source='depreciation' + source_ref=f"{asset_id}:{period}" so the UNIQUE lock
# makes every (asset, period) accrual exactly-once across replayed runs.
JOURNAL_SOURCE_DEPRECIATION = "depreciation"
INVOICE_SOURCE_MANUAL = "manual"
INVOICE_SOURCE_SALES_ORDER = "sales_order"
PAYMENT_SOURCE_MANUAL = "manual"

# ---------------------------------------------------------------------------
# Skip-auth paths (middleware bypass) - real mounted paths under /api/v1.
# ---------------------------------------------------------------------------
SKIP_AUTH_PATHS = frozenset(
    {
        f"{API_V1_PREFIX}/health",
        f"{API_V1_PREFIX}/ready",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)

# ---------------------------------------------------------------------------
# Multi-tenancy
# ---------------------------------------------------------------------------
# Platform-owned slugs never resolve to a tenant (mirrors identity). The
# routing contract is identical: Host subdomain in staging/production,
# X-Tenant-Slug header injected by nginx in dev/test.
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
