"""Canonical permission keys for the identity domain.

Platform-fixed catalog: these keys are the source of truth that role
definitions (``core/constants.py``) and the RBAC authorization service
reference. Keys follow the ``{scope}:{action}`` convention (e.g.
``users:write``).

A permission must be added here AND via migration before it can be assigned
to roles.
"""

from __future__ import annotations

# Full access within a tenant (owner role).
WILDCARD = "*"

# User management
USERS_READ = "users:read"
USERS_WRITE = "users:write"
USERS_DELETE = "users:delete"

# Role management
ROLES_READ = "roles:read"
ROLES_WRITE = "roles:write"

# Tenant / organization
TENANTS_READ = "tenants:read"
TENANTS_WRITE = "tenants:write"

# Sessions
SESSIONS_READ = "sessions:read"
SESSIONS_REVOKE = "sessions:revoke"

# Audit
AUDIT_READ = "audit:read"

# Security configuration
MFA_MANAGE = "mfa:manage"
SSO_MANAGE = "sso:manage"

# Organization settings
SETTINGS_READ = "settings:read"
SETTINGS_WRITE = "settings:write"

# ERP
ERP_INVOICE_READ = "erp.invoice.read"
ERP_INVOICE_APPROVE = "erp.invoice.approve"
ERP_PURCHASE_APPROVE = "erp.purchase.approve"
ERP_CRM_READ = "erp.crm.read"
ERP_CRM_WRITE = "erp.crm.write"
ERP_SALES_READ = "erp.sales.read"
ERP_SALES_WRITE = "erp.sales.write"
ERP_SALES_APPROVE = "erp.sales.approve"
ERP_INVENTORY_READ = "erp.inventory.read"
ERP_INVENTORY_WRITE = "erp.inventory.write"
ERP_INVENTORY_APPROVE = "erp.inventory.approve"
ERP_INVENTORY_AI_APPROVE = "erp.inventory.ai.approve"
ERP_FINANCE_READ = "erp.finance.read"
ERP_FINANCE_WRITE = "erp.finance.write"
ERP_HR_READ = "erp.hr.read"
ERP_HR_WRITE = "erp.hr.write"
ERP_HR_APPROVE = "erp.hr.approve"
ERP_PAYROLL_READ = "erp.payroll.read"
ERP_PAYROLL_WRITE = "erp.payroll.write"
ERP_PAYROLL_APPROVE = "erp.payroll.approve"

# AI assistant gate (docs/modules/skyrict-ai/inventory-ai-features.md §6.3).
# Checked by core BEFORE any /api/v1/ai/* request is forwarded to the
# ai-agent microservice. Same string as core's catalog so role grants stay
# portable across the platform.
ERP_AI_INVOKE = "erp.ai.invoke"

# HR & Payroll AI slice (docs/modules/skyrict-ai/hr-payroll-ai-features.md §3).
# L1 keys gate aggregate panels; L2 keys gate individual-level data.
ERP_HR_AI_READ = "erp.hr.ai.read"
ERP_HR_AI_INDIVIDUAL = "erp.hr.ai.individual"
ERP_HR_AI_ACKNOWLEDGE = "erp.hr.ai.acknowledge"
ERP_HR_AI_COPILOT = "erp.hr.ai.copilot"

# Employee self-service portal (own leave balances / requests only)
ERP_LEAVE_SELF = "erp.leave.self"

# AI Agents
AGENTS_READ = "agents:read"

# Market Intelligence
INTELLIGENCE_READ = "intelligence:read"

# Billing
BILLING_MANAGE = "billing.manage"

# Invitations
INVITATIONS_SEND = "invitations:send"

# Every catalogued permission, in catalog order.
CATALOG: tuple[str, ...] = (
    USERS_READ,
    USERS_WRITE,
    USERS_DELETE,
    ROLES_READ,
    ROLES_WRITE,
    TENANTS_READ,
    TENANTS_WRITE,
    SESSIONS_READ,
    SESSIONS_REVOKE,
    AUDIT_READ,
    MFA_MANAGE,
    SSO_MANAGE,
    SETTINGS_READ,
    SETTINGS_WRITE,
    ERP_INVOICE_READ,
    ERP_INVOICE_APPROVE,
    ERP_PURCHASE_APPROVE,
    ERP_CRM_READ,
    ERP_CRM_WRITE,
    ERP_SALES_READ,
    ERP_SALES_WRITE,
    ERP_SALES_APPROVE,
    ERP_INVENTORY_READ,
    ERP_INVENTORY_WRITE,
    ERP_INVENTORY_APPROVE,
    ERP_INVENTORY_AI_APPROVE,
    ERP_FINANCE_READ,
    ERP_FINANCE_WRITE,
    ERP_HR_READ,
    ERP_HR_WRITE,
    ERP_HR_APPROVE,
    ERP_PAYROLL_READ,
    ERP_PAYROLL_WRITE,
    ERP_PAYROLL_APPROVE,
    ERP_AI_INVOKE,
    ERP_HR_AI_READ,
    ERP_HR_AI_INDIVIDUAL,
    ERP_HR_AI_ACKNOWLEDGE,
    ERP_HR_AI_COPILOT,
    ERP_LEAVE_SELF,
    AGENTS_READ,
    INTELLIGENCE_READ,
    BILLING_MANAGE,
    INVITATIONS_SEND,
)

# Permission module groupings (for GET /permissions catalog endpoint)
# Each entry: (module_key, module_label, (permission_keys, ...))
PERMISSION_MODULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("user", "User management", (USERS_READ, USERS_WRITE, USERS_DELETE)),
    ("role", "Role management", (ROLES_READ, ROLES_WRITE)),
    ("tenant", "Tenant / organization", (TENANTS_READ, TENANTS_WRITE)),
    ("session", "Sessions", (SESSIONS_READ, SESSIONS_REVOKE)),
    ("audit", "Audit", (AUDIT_READ,)),
    ("security", "Security configuration", (MFA_MANAGE, SSO_MANAGE)),
    ("settings", "Organization settings", (SETTINGS_READ, SETTINGS_WRITE)),
    ("erp", "ERP", (ERP_INVOICE_READ, ERP_INVOICE_APPROVE, ERP_PURCHASE_APPROVE)),
    ("erp_crm", "ERP CRM", (ERP_CRM_READ, ERP_CRM_WRITE)),
    ("erp_sales", "ERP Sales", (ERP_SALES_READ, ERP_SALES_WRITE, ERP_SALES_APPROVE)),
    (
        "erp_inventory",
        "ERP Inventory",
        (ERP_INVENTORY_READ, ERP_INVENTORY_WRITE, ERP_INVENTORY_APPROVE, ERP_INVENTORY_AI_APPROVE),
    ),
    ("erp_finance", "ERP Finance", (ERP_FINANCE_READ, ERP_FINANCE_WRITE)),
    ("erp_hr", "ERP HR", (ERP_HR_READ, ERP_HR_WRITE, ERP_HR_APPROVE)),
    (
        "erp_payroll",
        "ERP Payroll",
        (ERP_PAYROLL_READ, ERP_PAYROLL_WRITE, ERP_PAYROLL_APPROVE),
    ),
    ("erp_ai", "ERP AI assistant", (ERP_AI_INVOKE,)),
    (
        "erp_hr_ai",
        "ERP HR & Payroll AI",
        (ERP_HR_AI_READ, ERP_HR_AI_INDIVIDUAL, ERP_HR_AI_ACKNOWLEDGE, ERP_HR_AI_COPILOT),
    ),
    ("erp_leave_self", "Employee self-service", (ERP_LEAVE_SELF,)),
    ("agents", "AI Agents", (AGENTS_READ,)),
    ("intelligence", "Market Intelligence", (INTELLIGENCE_READ,)),
    ("billing", "Billing", (BILLING_MANAGE,)),
    ("invitations", "User invitations", (INVITATIONS_SEND,)),
)


def _assert_catalog_union() -> None:
    """Ensure PERMISSION_MODULES and CATALOG stay in sync (fail-fast on drift)."""
    module_keys = {k for _, _, keys in PERMISSION_MODULES for k in keys}
    catalog_keys = set(CATALOG)
    if module_keys != catalog_keys:
        missing = catalog_keys - module_keys
        orphaned = module_keys - catalog_keys
        msg = "PERMISSION_MODULES <-> CATALOG mismatch:\n"
        if missing:
            msg += f"  Missing from PERMISSION_MODULES: {missing}\n"
        if orphaned:
            msg += f"  Orphaned in PERMISSION_MODULES: {orphaned}\n"
        raise ValueError(msg)


_assert_catalog_union()

__all__ = [
    "AGENTS_READ",
    "AUDIT_READ",
    "BILLING_MANAGE",
    "CATALOG",
    "ERP_AI_INVOKE",
    "ERP_CRM_READ",
    "ERP_CRM_WRITE",
    "ERP_FINANCE_READ",
    "ERP_FINANCE_WRITE",
    "ERP_HR_AI_ACKNOWLEDGE",
    "ERP_HR_AI_COPILOT",
    "ERP_HR_AI_INDIVIDUAL",
    "ERP_HR_AI_READ",
    "ERP_HR_APPROVE",
    "ERP_HR_READ",
    "ERP_HR_WRITE",
    "ERP_INVENTORY_AI_APPROVE",
    "ERP_INVENTORY_APPROVE",
    "ERP_INVENTORY_READ",
    "ERP_INVENTORY_WRITE",
    "ERP_INVOICE_APPROVE",
    "ERP_INVOICE_READ",
    "ERP_LEAVE_SELF",
    "ERP_PAYROLL_APPROVE",
    "ERP_PAYROLL_READ",
    "ERP_PAYROLL_WRITE",
    "ERP_PURCHASE_APPROVE",
    "ERP_SALES_APPROVE",
    "ERP_SALES_READ",
    "ERP_SALES_WRITE",
    "INTELLIGENCE_READ",
    "INVITATIONS_SEND",
    "MFA_MANAGE",
    "PERMISSION_MODULES",
    "ROLES_READ",
    "ROLES_WRITE",
    "SESSIONS_READ",
    "SESSIONS_REVOKE",
    "SETTINGS_READ",
    "SETTINGS_WRITE",
    "SSO_MANAGE",
    "TENANTS_READ",
    "TENANTS_WRITE",
    "USERS_DELETE",
    "USERS_READ",
    "USERS_WRITE",
    "WILDCARD",
]
