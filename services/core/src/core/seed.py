"""Database seeding — per-tenant HR/Payroll defaults (HR-DATA-001) and core RBAC roles.

Global reference data (currencies, permissions) is seeded by migration 0001;
the per-tenant defaults that CANNOT live in a migration (they are tenant-scoped
decisions) live here and are applied at tenant provisioning time:

  - the leave-type catalogue defaults: casual (accrual, 12 days/yr), sick
    (accrual, 8 days/yr), and unpaid (non-accrual ledger-only type);
  - the single ``erp_payroll_settings`` row per tenant (default currency from
    settings, zero PF/tax rates, nearest rounding);
  - the five system roles in ``core_roles`` (ERP grants per the HR & Payroll
    design doc section 2.4) — the role catalog ``require_permission`` resolves
    through ``core_user_roles``.

EMP-/PR- record-numbering seeds are deliberately NOT here: ``erp_sequences``
now exists (migration 0006) but the per-tenant counter seed rows land with the
HR service ticket, which owns the numbering scheme.

Idempotent: safe to re-run — existing rows are left untouched (system-role
permits are appended, never removed).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from core.core.config import settings
from core.core.permissions import (
    ERP_CRM_READ,
    ERP_CRM_WRITE,
    ERP_HR_AI_ACKNOWLEDGE,
    ERP_HR_AI_COPILOT,
    ERP_HR_AI_READ,
    ERP_HR_APPROVE,
    ERP_HR_READ,
    ERP_HR_WRITE,
    ERP_LEAVE_SELF,
    ERP_PAYROLL_APPROVE,
    ERP_PAYROLL_READ,
    ERP_PAYROLL_WRITE,
    ERP_SALES_APPROVE,
    ERP_SALES_READ,
    ERP_SALES_WRITE,
    WILDCARD,
)
from core.db.session import async_session_factory
from core.features.hr.models.leave_type import LeaveTypeModel
from core.features.payroll.models.payroll_run import PayrollRounding
from core.features.payroll.models.payroll_settings import PayrollSettingsModel
from core.models.core_role import CoreRoleModel

if TYPE_CHECKING:
    import uuid

logger = structlog.get_logger("core.seed")


@dataclass(frozen=True)
class LeaveTypeDefault:
    """One default leave-type catalogue entry."""

    code: str
    name: str
    is_accrual: bool
    accrual_days_per_year: int | None


LEAVE_TYPE_DEFAULTS: tuple[LeaveTypeDefault, ...] = (
    LeaveTypeDefault("annual", "Annual Leave", True, 20),
    LeaveTypeDefault("casual", "Casual Leave", True, 12),
    LeaveTypeDefault("sick", "Sick Leave", True, 8),
    LeaveTypeDefault("unpaid", "Unpaid Leave", False, None),
)


@dataclass(frozen=True)
class PayrollDefaults:
    """Shape of the single per-tenant payroll settings row."""

    default_currency: str
    pf_rate: Decimal
    tax_rate: Decimal
    rounding: PayrollRounding


async def seed_tenant_hr_defaults(tenant_id: uuid.UUID) -> None:
    """Idempotently seed the HR/Payroll defaults for one tenant."""
    async with async_session_factory() as session:
        existing_types = {
            code
            for (code,) in (
                await session.execute(
                    select(LeaveTypeModel.code).where(LeaveTypeModel.tenant_id == tenant_id)
                )
            ).all()
        }

        inserted_types = 0
        for defaults in LEAVE_TYPE_DEFAULTS:
            if defaults.code in existing_types:
                continue
            session.add(
                LeaveTypeModel(
                    tenant_id=tenant_id,
                    code=defaults.code,
                    name=defaults.name,
                    is_accrual=defaults.is_accrual,
                    accrual_days_per_year=defaults.accrual_days_per_year,
                )
            )
            inserted_types += 1
        if inserted_types:
            logger.info("seed.leave_types.created", tenant_id=str(tenant_id), count=inserted_types)

        existing_settings = await session.execute(
            select(PayrollSettingsModel.id).where(PayrollSettingsModel.tenant_id == tenant_id)
        )
        if existing_settings.scalar_one_or_none() is None:
            session.add(
                PayrollSettingsModel(
                    tenant_id=tenant_id,
                    default_currency=settings.DEFAULT_CURRENCY,
                    pf_rate=Decimal("0"),
                    tax_rate=Decimal("0"),
                    rounding=PayrollRounding.NEAREST,
                )
            )
            logger.info("seed.payroll_settings.created", tenant_id=str(tenant_id))

        await session.commit()


# System roles mirrored into ``core_roles`` per tenant (design doc section 2.4).
# Keys come from ``core_permissions`` — the platform-fixed catalog seeded by
# migration 0006 with the six ``erp.hr.*`` / ``erp.payroll.*`` keys; the
# ``erp.crm.*`` / ``erp.sales.*`` grants mirror identity's SYSTEM_ROLE_DEFINITIONS
# (services/identity/src/identity/core/constants.py) so role grants stay portable
# across the platform.
CORE_SYSTEM_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tenant_owner", (WILDCARD,)),
    (
        "organization_admin",
        (
            ERP_HR_READ,
            ERP_HR_WRITE,
            ERP_HR_APPROVE,
            ERP_PAYROLL_READ,
            ERP_PAYROLL_WRITE,
            ERP_PAYROLL_APPROVE,
            ERP_CRM_READ,
            ERP_CRM_WRITE,
            ERP_SALES_READ,
            ERP_SALES_WRITE,
            ERP_SALES_APPROVE,
            ERP_HR_AI_READ,
            ERP_HR_AI_ACKNOWLEDGE,
            ERP_HR_AI_COPILOT,
        ),
    ),
    (
        "department_manager",
        (
            ERP_HR_READ,
            ERP_HR_WRITE,
            ERP_PAYROLL_READ,
            ERP_CRM_READ,
            ERP_CRM_WRITE,
            ERP_SALES_READ,
            ERP_SALES_WRITE,
            ERP_HR_AI_READ,
            ERP_HR_AI_ACKNOWLEDGE,
            ERP_HR_AI_COPILOT,
        ),
    ),
    ("standard_user", (ERP_HR_READ, ERP_CRM_READ, ERP_SALES_READ)),
    (
        "auditor",
        (
            ERP_HR_READ,
            ERP_PAYROLL_READ,
            ERP_CRM_READ,
            ERP_SALES_READ,
            ERP_HR_AI_READ,
        ),
    ),
    # Employee self-service: portal-only role (own leave balances/requests).
    # Deliberately holds zero dashboard permissions; mirrors identity's
    # SYSTEM_ROLE_DEFINITIONS so invite grants stay portable.
    ("employee_self_service", (ERP_LEAVE_SELF,)),
)


async def seed_core_roles_for_tenant(tenant_id: uuid.UUID) -> None:
    """Idempotently seed the system roles for one tenant's core RBAC.

    Populates ``core_roles`` — the role catalog ``require_permission`` resolves
    through ``core_user_roles`` — with the five system roles and their ERP
    grants (design doc section 2.4). Existing rows are merged, never reset:
    ``is_system_role`` is forced to True and missing keys appended, so
    tenant-specific grants on a system role are preserved.
    """
    async with async_session_factory() as session:
        existing = {
            role.name: role
            for role in (
                await session.execute(
                    select(CoreRoleModel).where(CoreRoleModel.tenant_id == tenant_id)
                )
            ).scalars()
        }

        created = 0
        for name, permissions in CORE_SYSTEM_ROLES:
            role = existing.get(name)
            if role is None:
                session.add(
                    CoreRoleModel(
                        tenant_id=tenant_id,
                        name=name,
                        permissions=list(permissions),
                        is_system_role=True,
                    )
                )
                created += 1
            else:
                role.is_system_role = True
                role.permissions = list(dict.fromkeys(role.permissions + list(permissions)))
        if created:
            logger.info("seed.core_roles.created", tenant_id=str(tenant_id), count=created)
        await session.commit()
