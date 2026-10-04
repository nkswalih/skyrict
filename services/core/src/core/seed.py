"""Database seeding - per-tenant defaults (HR/Payroll + Finance) and core RBAC roles.

Global reference data (currencies, permissions) is seeded by migration 0001;
the per-tenant defaults that CANNOT live in a migration (they are tenant-scoped
decisions) live here and are applied at tenant provisioning time:

  **HR / Payroll:**
  - the leave-type catalogue defaults: casual (accrual, 12 days/yr), sick
    (accrual, 8 days/yr), and unpaid (non-accrual ledger-only type);
  - the single ``erp_payroll_settings`` row per tenant (default currency from
    settings, zero PF/tax rates, nearest rounding);
  - the Phase-1 reporting pack in ``erp_report_definitions`` (the SAME
    ``core.features.reporting.seeds`` catalog that migrations 0036/0039 apply
    for pre-existing tenants; provisioning reconciles, so catalog updates
    reach existing tenants too);
  - the five system roles in ``core_roles`` (ERP grants per the HR & Payroll
    design doc section 2.4) - the role catalog ``require_permission`` resolves
    through ``core_user_roles``.

  **Finance (SKY-94 / SKY-96):**
  - the default chart of accounts in ``erp_chart_of_accounts`` (9 accounts
    covering sales, COGS, and the payroll-accrual bridge) seeded on
    every new tenant so sales order fulfilment and payroll accrual work
    out-of-the-box.  Defined in ``DEFAULT_CHART_ACCOUNTS`` below; backfilled
    for pre-existing tenants by migration 0063.

EMP-/PR- record-numbering seeds are deliberately NOT here: ``erp_sequences``
now exists (migration 0006) but the per-tenant counter seed rows land with the
HR service ticket, which owns the numbering scheme.

Idempotent: safe to re-run - existing rows are left untouched when in sync
(reporting definitions are reconciled only when the canonical catalog is
newer; system-role permits are appended, never removed).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.core.config import settings
from core.core.permissions import (
    ERP_AI_COACHING_READ,
    ERP_AI_COACHING_REVIEW,
    ERP_AI_GUARDIAN_READ,
    ERP_AI_GUARDIAN_REVIEW,
    ERP_AI_INVOKE,
    ERP_CRM_READ,
    ERP_CRM_WRITE,
    ERP_FINANCE_APPROVE,
    ERP_HR_AI_ACKNOWLEDGE,
    ERP_HR_AI_COPILOT,
    ERP_HR_AI_EVAL,
    ERP_HR_AI_MANAGEMENT,
    ERP_HR_AI_READ,
    ERP_HR_APPROVE,
    ERP_HR_READ,
    ERP_HR_WRITE,
    ERP_INVENTORY_ADJUST,
    ERP_INVENTORY_ADJUST_APPROVE,
    ERP_INVENTORY_COST,
    ERP_INVENTORY_SUPPLIERS_READ,
    ERP_INVENTORY_SUPPLIERS_WRITE,
    ERP_LEAVE_SELF,
    ERP_PAYROLL_AI_APPROVE,
    ERP_PAYROLL_AI_NOTIFY,
    ERP_PAYROLL_AI_READ,
    ERP_PAYROLL_AI_RUN,
    ERP_PAYROLL_APPROVE,
    ERP_PAYROLL_READ,
    ERP_PAYROLL_WRITE,
    ERP_REPORTS_CREATE,
    ERP_REPORTS_READ,
    ERP_SALES_APPROVE,
    ERP_SALES_READ,
    ERP_SALES_WRITE,
    WILDCARD,
)
from core.db.session import async_session_factory
from core.domain.value_objects import AccountType
from core.features.approval_workflow.definition_repository import (
    ApprovalWorkflowDefinitionRepository,
)
from core.features.approval_workflow.dsl import (
    AmountBelowCondition,
    AutoApprovalRule,
    EscalationPolicy,
    PermissionAssignee,
    RoutingStrategy,
    SlaPolicy,
    WorkflowDefinition,
    WorkflowStep,
)
from core.features.finance.models.chart_of_account import ErpChartOfAccountModel
from core.features.hr.models.leave_type import LeaveTypeModel
from core.features.payroll.models.payroll_run import PayrollRounding
from core.features.payroll.models.payroll_settings import PayrollSettingsModel
from core.features.reporting.models.report_definition import ErpReportDefinitionModel
from core.features.reporting.seeds import PHASE_1_REPORT_SEEDS, is_seed_stale
from core.features.reporting.validation import require_tenant_filter, validate_read_only_sql
from core.models.core_role import CoreRoleModel

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


@dataclass(frozen=True)
class DefaultChartAccount:
    """One account in a tenant's default chart of accounts.

    This is the tenant-scoped source of truth for the finance module's
    mandatory accounts (SKY-94/SKY-96).  It mirrors the demo chart entries in
    ``seed_demo.ACCOUNT_ROWS`` but is the *minimum* set the runtime
    (``core.core.constants``) resolves by code - sales revenue ``4000``,
    COGS ``5000``, the inventory/payables/receivables balance-sheet accounts,
    and the payroll-accrual bridge.
    """

    code: str
    name: str
    account_type: AccountType


DEFAULT_CHART_ACCOUNTS: tuple[DefaultChartAccount, ...] = (
    # --- Asset accounts (always debited when an asset grows) ---
    DefaultChartAccount("1100", "Accounts Receivable", AccountType.ASSET),
    DefaultChartAccount("1200", "Cash", AccountType.ASSET),
    DefaultChartAccount("1300", "Inventory Asset", AccountType.ASSET),
    # --- Liability accounts (always credited when a liability grows) ---
    DefaultChartAccount("2010", "Accrued Salaries", AccountType.LIABILITY),
    DefaultChartAccount("2020", "Tax Payable", AccountType.LIABILITY),
    DefaultChartAccount("2110", "Accounts Payable", AccountType.LIABILITY),
    # --- Revenue accounts ---
    DefaultChartAccount("4000", "Sales Revenue", AccountType.REVENUE),
    # --- Expense accounts ---
    DefaultChartAccount("5000", "Cost of Goods Sold", AccountType.EXPENSE),
    DefaultChartAccount("5010", "Salaries Expense", AccountType.EXPENSE),
)


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


async def seed_tenant_finance_defaults(tenant_id: uuid.UUID) -> None:
    """Idempotently seed the default chart of accounts for one tenant.

    SKY-94/SKY-96: every tenant gets the mandatory finance accounts so sales
    order fulfilment (which resolves ``4000`` revenue and ``5000`` COGS) and
    payroll accrual work out-of-the-box.  Without these rows,
    ``features/finance/service.py`` raises ``NotFoundError`` for the COGS
    account code during ``post_cogs_for_order``.

    The migration 0063 backfills pre-existing tenants; {cli,_seed_tenant}
    calls this at provisioning time for every new tenant.  Both paths use the
    same ``DEFAULT_CHART_ACCOUNTS`` catalog above, keeping demo seeding
    (``seed_demo.ACCOUNT_ROWS``), provisioning, and backfill consistent.

    Idempotent and concurrency-safe: existing codes are left untouched and a
    ``(tenant_id, code)`` unique constraint plus ``ON CONFLICT ... DO NOTHING``
    absorbs a provisioning race with the first concurrent write.

    Uses a parameterized Core insert (no string-built SQL) so the statement is
    safe under both asyncpg and Bandit's hardcoded-SQL scan.
    """
    async with async_session_factory() as session:
        await session.execute(
            pg_insert(ErpChartOfAccountModel)
            .values(
                [
                    {
                        "tenant_id": tenant_id,
                        "id": uuid.uuid4(),
                        "code": account.code,
                        "name": account.name,
                        "account_type": account.account_type,
                        "is_active": True,
                    }
                    for account in DEFAULT_CHART_ACCOUNTS
                ]
            )
            .on_conflict_do_nothing(
                index_elements=[ErpChartOfAccountModel.tenant_id, ErpChartOfAccountModel.code]
            )
        )
        await session.commit()
        logger.info(
            "seed.finance.chart.seeded",
            tenant_id=str(tenant_id),
            expected=len(DEFAULT_CHART_ACCOUNTS),
        )


# System roles mirrored into ``core_roles`` per tenant (design doc section 2.4).
# Keys come from ``core_permissions`` - the platform-fixed catalog seeded by
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
            ERP_AI_INVOKE,
            ERP_HR_AI_READ,
            ERP_HR_AI_ACKNOWLEDGE,
            ERP_HR_AI_COPILOT,
            ERP_PAYROLL_AI_READ,
            ERP_PAYROLL_AI_RUN,
            ERP_PAYROLL_AI_NOTIFY,
            ERP_PAYROLL_AI_APPROVE,
            ERP_FINANCE_APPROVE,
            ERP_INVENTORY_ADJUST,
            ERP_INVENTORY_ADJUST_APPROVE,
            ERP_INVENTORY_COST,
            ERP_INVENTORY_SUPPLIERS_READ,
            ERP_INVENTORY_SUPPLIERS_WRITE,
            ERP_REPORTS_CREATE,
            ERP_REPORTS_READ,
            ERP_HR_AI_EVAL,
            ERP_HR_AI_MANAGEMENT,
            ERP_AI_COACHING_READ,
            ERP_AI_COACHING_REVIEW,
            ERP_AI_GUARDIAN_READ,
            ERP_AI_GUARDIAN_REVIEW,
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
            ERP_REPORTS_READ,
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
            ERP_PAYROLL_AI_READ,
            ERP_REPORTS_READ,
        ),
    ),
    # Employee self-service: portal-only role (own leave balances/requests).
    # Deliberately holds zero dashboard permissions; mirrors identity's
    # SYSTEM_ROLE_DEFINITIONS so invite grants stay portable.
    ("employee_self_service", (ERP_LEAVE_SELF,)),
)


async def seed_core_roles_for_tenant(tenant_id: uuid.UUID) -> None:
    """Idempotently seed the system roles for one tenant's core RBAC.

    Populates ``core_roles`` - the role catalog ``require_permission`` resolves
    through ``core_user_roles`` - with the five system roles and their ERP
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


async def seed_reporting_defaults(tenant_id: uuid.UUID) -> None:
    """Reconcile the Phase-1 report definitions for one tenant.

    Applies the canonical ``PHASE_1_REPORT_SEEDS`` pack - the same definitions
    migration 0036/0039 insert for pre-existing tenants - so a newly
    provisioned tenant is indistinguishable from one that pre-dates the
    reporting data layer. Each definition is validated read-only before
    insert/update.

    Reconcile (not insert-only): missing slugs are inserted, and an existing
    definition that is stale - older ``version`` than the seed, or stored SQL
    diverging from the canonical seed after whitespace normalization - is
    refreshed in place and its version bumped. Identical rows are left
    untouched so re-runs are stable and never rewrite what is already in
    sync. This is what keeps a catalog improvement (e.g. ``ar_aging`` gaining
    ``outstanding``) from silently never reaching already-provisioned tenants.
    """
    async with async_session_factory() as session:
        existing = {
            model.slug: model
            for model in (
                await session.execute(
                    select(ErpReportDefinitionModel).where(
                        ErpReportDefinitionModel.tenant_id == tenant_id
                    )
                )
            ).scalars()
        }

        inserted = 0
        updated = 0
        for seed in PHASE_1_REPORT_SEEDS:
            validate_read_only_sql(seed.sql, seed.params)
            require_tenant_filter(seed.sql)
            model = existing.get(seed.slug)
            if model is None:
                session.add(
                    ErpReportDefinitionModel(
                        tenant_id=tenant_id,
                        slug=seed.slug,
                        title=seed.title,
                        module=seed.module,
                        description=seed.description,
                        sql=seed.sql,
                        params=list(seed.params),
                        permission_key=seed.permission_key,
                        version=seed.version,
                    )
                )
                inserted += 1
                continue
            if is_seed_stale(seed, version=model.version, sql=model.sql):
                model.title = seed.title
                model.module = seed.module
                model.description = seed.description
                model.sql = seed.sql
                model.params = list(seed.params)
                model.permission_key = seed.permission_key
                model.version = seed.version
                updated += 1
        if inserted or updated:
            logger.info(
                "seed.reporting_definitions.reconciled",
                tenant_id=str(tenant_id),
                inserted=inserted,
                updated=updated,
            )
        await session.commit()


# ---------------------------------------------------------------------------
# Approval workflow definition defaults (SKY-92)
# ---------------------------------------------------------------------------

#: Resource type keyed by the finance coordinator (finance/approval.py).
JE_APPROVAL_RESOURCE_TYPE = "journal_entry"

#: Resource type keyed by the payroll coordinator (payroll/approval.py).
PAYROLL_APPROVAL_RESOURCE_TYPE = "payroll_run"


async def seed_approval_workflow_defaults(tenant_id: uuid.UUID) -> None:
    """Idempotently seed the built-in journal-entry + payroll-run approval definitions.

    The definitions every newly provisioned tenant starts with (SKY-92
    decision 6). The engine stays OFF until the tenant opts in via the
    ``erp_tenant_settings`` flags, but the definitions are provisioned with
    the normal tenant bootstrap so ``cli seed --tenant-id`` is all an
    operator needs before flipping the flag.

    Journal-entry definition contract:

    - routing amount is the entry's total debit, supplied by finance as an
      exact ``Decimal`` (never floats);
    - amounts below ``10,000`` auto-approve (system actor audit + immediate
      finance posting);
    - amounts at-or-above ``10,000`` route to holders of the
      ``erp.finance.approve`` permission, with a 24h SLA, the same group as
      the escalation target, delegation allowed, and AI-assisted routing
      (advisory only - the AI never decides or selects an unauthorized
      approver).

    Payroll-run definition contract - the same shape, keyed on the run's
    total NET (exact ``Decimal``) and assigned to ``erp.payroll.approve``.

    Skipped when the tenant already has an ACTIVE definition for a resource:
    operators can hand-tune the definition later and re-seeding must never
    overwrite their workflow.
    """
    async with async_session_factory() as session:
        definitions = ApprovalWorkflowDefinitionRepository(session)

        active_je = await definitions.get_active(tenant_id, JE_APPROVAL_RESOURCE_TYPE)
        if active_je is None:
            je_definition = WorkflowDefinition(
                name="Journal entry approval",
                resource_type=JE_APPROVAL_RESOURCE_TYPE,
                version=1,
                steps=[
                    WorkflowStep(
                        key="finance_approval",
                        assignee=PermissionAssignee(permission=ERP_FINANCE_APPROVE),
                        routing=RoutingStrategy.AI_ASSISTED,
                        auto_approval=AutoApprovalRule(
                            when=AmountBelowCondition(amount=Decimal("10000.00"))
                        ),
                        sla=SlaPolicy(
                            hours=24,
                            reminder_before_hours=4,
                            escalation=EscalationPolicy(
                                assignee=PermissionAssignee(permission=ERP_FINANCE_APPROVE)
                            ),
                        ),
                    )
                ],
            )
            je_draft = await definitions.create_draft(
                tenant_id=tenant_id,
                name="Journal entry approval",
                resource_type=JE_APPROVAL_RESOURCE_TYPE,
                definition=je_definition.model_dump(mode="json"),
            )
            await definitions.activate(tenant_id, je_draft.id)
            logger.info(
                "seed.approval_workflow.je_definition.seeded",
                tenant_id=str(tenant_id),
                version=je_draft.version,
            )

        active_pr = await definitions.get_active(tenant_id, PAYROLL_APPROVAL_RESOURCE_TYPE)
        if active_pr is None:
            pr_definition = WorkflowDefinition(
                name="Payroll run approval",
                resource_type=PAYROLL_APPROVAL_RESOURCE_TYPE,
                version=1,
                steps=[
                    WorkflowStep(
                        key="payroll_approval",
                        assignee=PermissionAssignee(permission=ERP_PAYROLL_APPROVE),
                        routing=RoutingStrategy.AI_ASSISTED,
                        auto_approval=AutoApprovalRule(
                            when=AmountBelowCondition(amount=Decimal("10000.00"))
                        ),
                        sla=SlaPolicy(
                            hours=24,
                            reminder_before_hours=4,
                            escalation=EscalationPolicy(
                                assignee=PermissionAssignee(permission=ERP_PAYROLL_APPROVE)
                            ),
                        ),
                    )
                ],
            )
            pr_draft = await definitions.create_draft(
                tenant_id=tenant_id,
                name="Payroll run approval",
                resource_type=PAYROLL_APPROVAL_RESOURCE_TYPE,
                definition=pr_definition.model_dump(mode="json"),
            )
            await definitions.activate(tenant_id, pr_draft.id)
            logger.info(
                "seed.approval_workflow.payroll_definition.seeded",
                tenant_id=str(tenant_id),
                version=pr_draft.version,
            )

        await session.commit()


async def sync_rbac_from_identity(tenant_id: uuid.UUID | None = None) -> None:
    """Sync user→role grants from identity's tables into core's RBAC tables.

    Both services share one database, so this reads identity's ``user_roles``
    (user→role grants) and ``roles`` (role catalog) and upserts into core's
    ``core_roles`` (role catalog) and ``core_user_roles`` (user→role grants).

    This bridges the gap where identity's seed creates ``user_roles`` rows
    (e.g. admin → tenant_owner) but core's ``seed_core_roles_for_tenant``
    only creates ``core_roles`` rows (role catalog) - never the user→role
    grants that ``require_permission`` resolves through.

    Idempotent: safe to re-run on every startup. Core's role IDs are never
    overwritten (preserving FK references). Role permission arrays are
    REPLACED from identity (the authoritative catalog) on every boot, so
    edits - including removals - propagate. Grants are RECONCILED, never
    merged: missing grants are added and stale grants - rows identity no
    longer holds because a role was revoked or a member downgraded - are
    removed, so identity stays the single source of truth for who can do
    what.

    Args:
        tenant_id: Project a single tenant instead of every tenant. ``None``
            is the boot path and is unchanged: identical SQL, all three steps,
            every tenant. A tenant id runs the two INSERT steps for that
            tenant alone and SKIPS the revocation step.

    The scoped form is additive by construction - it can create a missing
    projection but never remove one. Step 3's DELETE is how IAM revocations
    reach core, and a background caller must not hold that power: its job is
    to restore access that is missing, and a tenant with no projection has no
    rows to revoke. Revocation stays on the boot path, where it is already
    reconciled on every deploy.
    """
    scoped = tenant_id is not None
    params: dict[str, uuid.UUID] = {"tenant_id": tenant_id} if tenant_id is not None else {}

    # Step 2 resolves the role NAME through a correlated subquery on identity's
    # roles. In the scoped form the lookup is pinned to the grant's own tenant:
    # user_roles has no composite FK to roles(tenant_id, id), so a row whose
    # denormalised tenant_id disagrees with its role's tenant is structurally
    # possible. Without the predicate such a row could match a same-named role
    # in the target tenant and silently grant the WRONG role; with it, the row
    # matches nothing, writes nothing, and is reported by the caller's
    # no-progress handling instead.
    role_name_lookup = (
        "  (SELECT r.name FROM roles r WHERE r.id = ur.role_id AND r.tenant_id = ur.tenant_id) "
        if scoped
        else "  (SELECT r.name FROM roles r WHERE r.id = ur.role_id) "
    )

    async with async_session_factory() as session:
        # Step 1: Sync role permissions from identity's roles into core_roles.
        # On conflict (same tenant + name), REPLACE permissions (never merge)
        # so permission removals propagate too - identity is authoritative for
        # role definitions. Core's own role `id` is NEVER overwritten - it is
        # the PK that core_user_roles FKs reference, so replacing it would
        # break existing grants.
        step1_sql = (
            "INSERT INTO core_roles (tenant_id, id, name, permissions, is_system_role) "
            "SELECT ir.tenant_id, ir.id, ir.name, ir.permissions, ir.is_system_role "
            "FROM roles ir"
        )
        if scoped:
            step1_sql += " WHERE ir.tenant_id = :tenant_id"
        step1_sql += (
            " ON CONFLICT (tenant_id, name) DO UPDATE SET "
            "permissions = EXCLUDED.permissions, "
            "is_system_role = EXCLUDED.is_system_role, updated_at = now()"
        )
        await session.execute(text(step1_sql), params)

        # Step 2: Upsert core_user_roles from identity's user_roles table.
        # Uses core's role_id (looked up by name) rather than identity's
        # role_id, because core's PK may differ from identity's if the role
        # was independently created. This keeps the FK valid.
        # B608: the only interpolation is `role_name_lookup`, one of two literals
        # chosen by `scoped` above - never caller input. Every caller-supplied
        # value reaches the database as a bound parameter.
        step2_sql = (
            "INSERT INTO core_user_roles (tenant_id, id, user_id, role_id, scope_id) "  # nosec B608
            "SELECT ur.tenant_id, gen_random_uuid(), ur.user_id, cr.id, ur.scope_id "
            "FROM user_roles ur "
            "JOIN core_roles cr ON cr.tenant_id = ur.tenant_id AND cr.name = "
            f"{role_name_lookup}"
        )
        # The predicate goes AFTER the join: a WHERE clause cannot precede a
        # JOIN in the FROM list.
        if scoped:
            step2_sql += "WHERE ur.tenant_id = :tenant_id "
        step2_sql += "ON CONFLICT DO NOTHING"
        await session.execute(text(step2_sql), params)

        # Step 3: Remove stale grants - rows whose (tenant, user, role, scope)
        # no longer exist in identity's user_roles. Identity is authoritative:
        # revocations must take effect here too. Without this, a role downgrade
        # in IAM (identity revokes the old grant) leaves the old grant in
        # core_user_roles forever, and every runtime check (ERP tools, the AI
        # agent greeting) keeps seeing the stale, broader access.
        #
        # Scoped to identity-managed tenants: a grant is only stale-eligible
        # when its tenant has an identity user_roles mirror - i.e. identity
        # has made a statement about that tenant. Tenants with NO mirror rows
        # (core tenants never provisioned through identity, or test fixtures
        # seeding core_user_roles directly) are left untouched; DELETE-ing
        # every grant absent from a non-authoritative mirror would strip their
        # grants and break authorization. Identity-managed tenants always have
        # mirror rows (the admin grant is seeded with the tenant), so real
        # revocations still propagate.
        #
        # Boot path only - see the scoped-form note in the docstring.
        if not scoped:
            await session.execute(
                text(
                    "DELETE FROM core_user_roles cur "
                    "WHERE EXISTS ("
                    "  SELECT 1 FROM user_roles ur_own "
                    "  WHERE ur_own.tenant_id = cur.tenant_id"
                    ") "
                    "AND NOT EXISTS ("
                    "  SELECT 1 "
                    "  FROM user_roles ur "
                    "  JOIN roles r ON r.id = ur.role_id "
                    "  JOIN core_roles cr ON cr.tenant_id = r.tenant_id AND cr.name = r.name "
                    "  WHERE ur.tenant_id = cur.tenant_id "
                    "    AND ur.user_id = cur.user_id "
                    "    AND cr.id = cur.role_id "
                    "    AND ur.scope_id IS NOT DISTINCT FROM cur.scope_id "
                    ")"
                )
            )

        await session.commit()

    if scoped:
        logger.info("seed.rbac_sync.tenant_completed", tenant_id=str(tenant_id))
    else:
        logger.info("seed.rbac_sync.completed")
