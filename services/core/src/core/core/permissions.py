"""Canonical ERP permission keys for the core service.

Platform-fixed catalog: these keys are the source of truth that role grants
(``core_roles.permissions``) and ``require_permission`` reference. Keys follow
the ``{domain}.{entity}.{action}`` convention (e.g. ``erp.inventory.read``).

A permission must be added here AND via migration before it can be assigned
to roles. Keys reused from identity's catalog (``erp.invoice.read``,
``erp.invoice.approve``, ``erp.purchase.approve``) are the SAME strings identity
seeds, so role grants stay portable across the platform.
``erp.invoice.approve``, ``erp.purchase.approve``, ``erp.crm.*``,
``erp.sales.*``) are the SAME strings identity seeds, so role grants stay
portable across the platform. The CRM keys and ``erp.sales.approve`` are
seeded into ``core_permissions`` by migration 0003. Inventory keys are
provisional until docs/modules/inventory-warehouse.md lands.
"""

from __future__ import annotations

# Full access within a tenant (owner role).
WILDCARD = "*"

# Inventory
ERP_INVENTORY_READ = "erp.inventory.read"
ERP_INVENTORY_WRITE = "erp.inventory.write"
ERP_INVENTORY_ADJUST = "erp.inventory.adjust"
ERP_INVENTORY_ADJUST_APPROVE = "erp.inventory.adjust.approve"
ERP_INVENTORY_AI_APPROVE = "erp.inventory.ai.approve"

# Purchasing
ERP_PURCHASE_READ = "erp.purchase.read"
ERP_PURCHASE_WRITE = "erp.purchase.write"
ERP_PURCHASE_APPROVE = "erp.purchase.approve"

# CRM (leads, opportunities, customers)
ERP_CRM_READ = "erp.crm.read"
ERP_CRM_WRITE = "erp.crm.write"

# Sales
ERP_SALES_READ = "erp.sales.read"
ERP_SALES_WRITE = "erp.sales.write"
ERP_SALES_APPROVE = "erp.sales.approve"

# Finance / invoicing
ERP_INVOICE_READ = "erp.invoice.read"
ERP_INVOICE_APPROVE = "erp.invoice.approve"
ERP_INVOICE_WRITE = "erp.invoice.write"

# Finance — full ledger/invoice/payment domain (successor to erp.invoice.*).
ERP_FINANCE_READ = "erp.finance.read"
ERP_FINANCE_WRITE = "erp.finance.write"
ERP_FINANCE_APPROVE = "erp.finance.approve"

# HR (design doc docs/design/hr-payroll.md)
ERP_HR_READ = "erp.hr.read"
ERP_HR_WRITE = "erp.hr.write"
ERP_HR_APPROVE = "erp.hr.approve"

# Payroll (design doc docs/design/hr-payroll.md)
ERP_PAYROLL_READ = "erp.payroll.read"
ERP_PAYROLL_WRITE = "erp.payroll.write"
ERP_PAYROLL_APPROVE = "erp.payroll.approve"

# AI assistant (docs/modules/skyrict-ai/inventory-ai-features.md §6.3).
# Gate checked by core BEFORE any /api/v1/ai/* request is forwarded to the
# ai-agent microservice - permissionless calls never reach the AI service.
ERP_AI_INVOKE = "erp.ai.invoke"

# HR & Payroll AI slice (docs/modules/skyrict-ai/hr-payroll-ai-features.md §3).
# Checked at the core edge for /api/v1/ai/hr/*. Same strings as identity's
# catalog so role grants stay portable across the platform.
ERP_HR_AI_READ = "erp.hr.ai.read"
ERP_HR_AI_INDIVIDUAL = "erp.hr.ai.individual"
ERP_HR_AI_ACKNOWLEDGE = "erp.hr.ai.acknowledge"
ERP_HR_AI_COPILOT = "erp.hr.ai.copilot"
ERP_HR_AI_EVAL = "erp.hr.ai.eval"

# Employee self-service portal (own leave balances/requests only; mirrors
# identity's catalog so the invite flow can grant it portably)
ERP_LEAVE_SELF = "erp.leave.self"

# Every catalogued permission, in catalog order.
CATALOG: tuple[str, ...] = (
    ERP_INVENTORY_READ,
    ERP_INVENTORY_WRITE,
    ERP_INVENTORY_ADJUST,
    ERP_INVENTORY_ADJUST_APPROVE,
    ERP_INVENTORY_AI_APPROVE,
    ERP_PURCHASE_READ,
    ERP_PURCHASE_WRITE,
    ERP_PURCHASE_APPROVE,
    ERP_CRM_READ,
    ERP_CRM_WRITE,
    ERP_SALES_READ,
    ERP_SALES_WRITE,
    ERP_SALES_APPROVE,
    ERP_INVOICE_READ,
    ERP_INVOICE_WRITE,
    ERP_INVOICE_APPROVE,
    ERP_FINANCE_READ,
    ERP_FINANCE_WRITE,
    ERP_FINANCE_APPROVE,
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
    ERP_HR_AI_EVAL,
    ERP_LEAVE_SELF,
)

# Permission module groupings.
# Each entry: (module_key, module_label, (permission_keys, ...))
PERMISSION_MODULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "inventory",
        "Inventory",
        (
            ERP_INVENTORY_READ,
            ERP_INVENTORY_WRITE,
            ERP_INVENTORY_ADJUST,
            ERP_INVENTORY_ADJUST_APPROVE,
            ERP_INVENTORY_AI_APPROVE,
        ),
    ),
    ("purchase", "Purchasing", (ERP_PURCHASE_READ, ERP_PURCHASE_WRITE, ERP_PURCHASE_APPROVE)),
    ("crm", "CRM", (ERP_CRM_READ, ERP_CRM_WRITE)),
    ("sales", "Sales", (ERP_SALES_READ, ERP_SALES_WRITE, ERP_SALES_APPROVE)),
    ("invoice", "Finance / invoicing", (ERP_INVOICE_READ, ERP_INVOICE_WRITE, ERP_INVOICE_APPROVE)),
    ("finance", "Finance", (ERP_FINANCE_READ, ERP_FINANCE_WRITE, ERP_FINANCE_APPROVE)),
    ("hr", "HR", (ERP_HR_READ, ERP_HR_WRITE, ERP_HR_APPROVE)),
    ("payroll", "Payroll", (ERP_PAYROLL_READ, ERP_PAYROLL_WRITE, ERP_PAYROLL_APPROVE)),
    ("ai", "AI assistant", (ERP_AI_INVOKE,)),
    (
        "hr_ai",
        "HR & Payroll AI",
        (
            ERP_HR_AI_READ,
            ERP_HR_AI_INDIVIDUAL,
            ERP_HR_AI_ACKNOWLEDGE,
            ERP_HR_AI_COPILOT,
            ERP_HR_AI_EVAL,
        ),
    ),
    ("leave_self", "Employee self-service", (ERP_LEAVE_SELF,)),
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
    "CATALOG",
    "ERP_AI_INVOKE",
    "ERP_CRM_READ",
    "ERP_CRM_WRITE",
    "ERP_FINANCE_APPROVE",
    "ERP_FINANCE_READ",
    "ERP_FINANCE_WRITE",
    "ERP_HR_AI_ACKNOWLEDGE",
    "ERP_HR_AI_COPILOT",
    "ERP_HR_AI_EVAL",
    "ERP_HR_AI_INDIVIDUAL",
    "ERP_HR_AI_READ",
    "ERP_HR_APPROVE",
    "ERP_HR_READ",
    "ERP_HR_WRITE",
    "ERP_INVENTORY_ADJUST",
    "ERP_INVENTORY_ADJUST_APPROVE",
    "ERP_INVENTORY_AI_APPROVE",
    "ERP_INVENTORY_READ",
    "ERP_INVENTORY_WRITE",
    "ERP_INVOICE_APPROVE",
    "ERP_INVOICE_READ",
    "ERP_INVOICE_WRITE",
    "ERP_LEAVE_SELF",
    "ERP_PAYROLL_APPROVE",
    "ERP_PAYROLL_READ",
    "ERP_PAYROLL_WRITE",
    "ERP_PURCHASE_APPROVE",
    "ERP_PURCHASE_READ",
    "ERP_PURCHASE_WRITE",
    "ERP_SALES_APPROVE",
    "ERP_SALES_READ",
    "ERP_SALES_WRITE",
    "PERMISSION_MODULES",
    "WILDCARD",
]
