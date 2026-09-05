"""Domain entities - pure Python, no framework dependencies.

These are the in-memory representations the repository layer maps ORM models
to/from. They are plain (immutable) dataclasses so services can reason about
tenant-scoped RBAC grants without touching SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from core.core.constants import (
    AttendanceStatus,
    EmploymentStatus,
    LeaveRequestStatus,
    PayImpact,
    PayrollJeBridgeStatus,
    PayrollRounding,
    PayrollRunStatus,
)
from core.domain.value_objects import (
    ActivityKind,
    CreditCheckResult,
    CrmEntityType,
    CrmTimelineEventType,
    LeadStatus,
    Money,
    OpportunityStage,
    OrderStatus,
)

if TYPE_CHECKING:
    import uuid
    from datetime import date, datetime

    from core.domain.value_objects import (
        AccountType,
        EntryStatus,
        InvoiceStatus,
        PaymentStatus,
        StockMovementType,
    )


@dataclass(frozen=True)
class CorePermission:
    """A platform-fixed permission key (e.g. ``erp.invoice.read``).

    Global - not tenant-scoped: the catalog is the same for every tenant.
    """

    key: str
    description: str = ""


@dataclass(frozen=True)
class CoreRole:
    """A tenant-scoped role holding a set of permission grants.

    ``permissions`` holds granted permission keys. The wildcard ``"*"`` grants
    every key in the catalog (owner role).
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    permissions: tuple[str, ...] = ()
    is_system_role: bool = False


@dataclass(frozen=True)
class CoreUserRole:
    """A tenant-scoped grant of one role to one user.

    ``user_id`` references an identity-service user (no FK at the DB level -
    identity owns users).
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    scope_id: uuid.UUID | None = field(default=None)


@dataclass(frozen=True)
class Product:
    """A tenant-scoped sellable/countable item (soft-deletable via ``is_active``).

    Prices are ``Money`` amounts so currency validation happens at construction,
    and the ORM layer splits them into a Numeric column + currency code.
    """

    tenant_id: uuid.UUID
    sku: str
    name: str
    category: str | None = None
    unit: str | None = None
    cost_price: Money = field(default_factory=lambda: Money.zero("USD"))
    sell_price: Money = field(default_factory=lambda: Money.zero("USD"))
    reorder_point: Decimal = Decimal("0")
    is_active: bool = True
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Warehouse:
    """A tenant-scoped storage location (soft-deletable via ``is_active``)."""

    tenant_id: uuid.UUID
    name: str
    location: str | None = None
    is_active: bool = True
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class StockLevel:
    """Materialized current stock for one product in one warehouse.

    ``qty_on_hand`` = ledger sum of non-reservation movements; ``qty_reserved``
    = net of reservation/release movements. The DB CHECK ``0 <= qty_reserved
    <= qty_on_hand`` makes over-reservation impossible at the constraint level.
    """

    tenant_id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    qty_on_hand: Decimal = Decimal("0")
    qty_reserved: Decimal = Decimal("0")
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class StockMovement:
    """One immutable ledger entry - insert-only, never updated or deleted.

    ``qty`` is signed (negative for issues/outflows). ``(ref_type, ref_id)``
    identifies the source document line for idempotency probes; combined with
    ``warehouse_id`` it is unique per tenant so a transfer pair can share a ref.
    """

    tenant_id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    movement_type: StockMovementType
    qty: Decimal
    ref_type: str
    ref_id: str
    id: uuid.UUID | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ErpSequence:
    """A per-tenant monotonic counter for one document numbering sequence.

    Services claim the next value via ``SequenceRepository.next_value`` (a
    row-locking ``UPDATE ... SET current_value = current_value + 1 RETURNING``),
    so consecutive numbers are race-safe and never reused.
    """

    tenant_id: uuid.UUID
    entity: str
    current_value: int = 0
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AuditLogEntry:
    """One immutable core (ERP) audit event in the tenant's hash chain.

    ``hash`` / ``prev_hash`` are computed by the DB trigger on INSERT and are
    ``None`` until then. Append-only: never update or delete.
    """

    tenant_id: uuid.UUID
    action: str
    target: str
    actor_user_id: uuid.UUID | None = None
    details: dict[str, object] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    id: uuid.UUID | None = None
    hash: str | None = None
    prev_hash: str | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# HR & Payroll entities (HR-BE-002) - pure domain, no framework dependencies.
# The repository layer maps these to/from the ORM models under
# ``features/{hr,payroll}/models/``.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Department:
    """An organizational unit within a tenant (soft-deletable via ``is_active``)."""

    tenant_id: uuid.UUID
    name: str
    manager_employee_id: uuid.UUID | None = None
    is_active: bool = True
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Employee:
    """A person employed within a tenant.

    ``employment_status`` is the single source of employment truth - there is
    deliberately no separate ``is_active`` flag. ``termination_date`` is
    required when status is ``terminated``.
    """

    tenant_id: uuid.UUID
    employee_number: str
    first_name: str
    last_name: str
    job_title: str
    hire_date: date
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    email: str | None = None
    phone: str | None = None
    user_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    termination_date: date | None = None
    bank_account: str | None = None
    bank_name: str | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class BenefitElection:
    """A tenant-scoped benefit plan election for one employee.

    ``effective_from`` is the date the election takes effect. The payroll
    pre-flight ``benefit_elections`` warning reads the enrolled elections for a
    pay period to surface roster employees holding none before a run commits.
    """

    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    effective_from: date
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class LeaveType:
    """Tenant-scoped leave catalogue entry (per-tenant accrual policy)."""

    tenant_id: uuid.UUID
    code: str
    name: str
    is_accrual: bool
    accrual_days_per_year: int | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class LeaveRequest:
    """A leave request raised by an employee and its approval state.

    ``days`` is derived (``end_date - start_date + 1``), computed server-side.
    """

    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    leave_type: str
    start_date: date
    end_date: date
    days: int
    status: LeaveRequestStatus = LeaveRequestStatus.PENDING
    reason: str | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class LeaveMovement:
    """One immutable entry in the leave ledger for a single employee.

    ``qty`` is signed (``+`` accrued/refunded, ``-`` approved/used) and must
    never be zero. Append-only: no update, no delete.
    """

    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    leave_type: str
    qty: int
    ref_type: str
    ref_id: str | None = None
    reason: str | None = None
    id: uuid.UUID | None = None
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class LeaveBalance:
    """Materialized current balance for one employee + leave type.

    Only accrual leave types have balance rows; ``balance`` is recomputed from
    the ledger and can never be negative (service + DB CHECK).
    """

    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    leave_type: str
    balance: int = 0
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class LeavePolicy:
    """Tenant-scoped leave policy - replaces per-type accrual config.

    Defines annual allotments for casual and sick leave. Effective from a
    chosen date; policy changes apply at the next Jan-1 reset (lazy accrual
    gated by idempotency: once a year's accrual exists, it is never
    re-generated).
    """

    tenant_id: uuid.UUID
    casual_days_per_year: int
    sick_days_per_year: int
    effective_from: date
    last_accrual_year: int | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AttendanceRecord:
    """One work day's attendance for an employee.

    ``pay_impact`` is derived from ``status`` by the service (on_time -> full,
    late -> half, absent -> none) - never trusted from clients. One record per
    (employee, work_date); corrections upsert the existing day.
    """

    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    work_date: date
    status: AttendanceStatus
    pay_impact: PayImpact
    note: str | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Compensation:
    """An effective-dated salary record for an employee.

    The row effective at or before period end (``is_active = true``, latest
    ``effective_from``) is used by payroll. ``monthly_salary`` is ``Money`` so
    currency is validated at construction.
    """

    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    monthly_salary: Money
    effective_from: date
    is_active: bool = True
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class PayrollRun:
    """A payroll run covering one tenant and one monthly period.

    ``total_gross``/``total_net`` are None until the run is computed; a
    zero-dollar run must stay distinct from a not-yet-computed run.
    """

    tenant_id: uuid.UUID
    run_code: str
    period_start: date
    period_end: date
    status: PayrollRunStatus = PayrollRunStatus.DRAFT
    total_gross: Money | None = None
    total_net: Money | None = None
    computed_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    paid_by: uuid.UUID | None = None
    computed_at: datetime | None = None
    approved_at: datetime | None = None
    paid_at: datetime | None = None
    void_reason: str | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Employees excluded from the compute with the reason (JSON list of
    # {"employee_id": str, "reason": str}), set at compute time (gap #6).
    skipped_employees: list[dict[str, str]] | None = None

    # Payroll→Finance accrual JE bridge state (Commit 4): none/pending/draft.
    je_bridge_status: PayrollJeBridgeStatus = PayrollJeBridgeStatus.NONE


@dataclass(frozen=True)
class Payslip:
    """One employee's payslip view inside a run (HR-AUT-001, Commit 4).

    ``gross``/``deductions``/``net`` mirror the run's frozen entry; the
    employee attributes denormalize the roster so the payslip endpoint needs no
    separate employee lookup.
    """

    tenant_id: uuid.UUID
    run_id: uuid.UUID
    employee_id: uuid.UUID
    employee_number: str
    employee_name: str
    gross: Money
    deductions: Money
    net: Money


@dataclass(frozen=True)
class PayslipReview:
    """Versioned payslip review row with approval lifecycle (HR-AUT-001, Commit 2).

    Every computed payslip is materialized as a ``draft`` review row on compute.
    An admin approves or rejects it; re-approval after correction creates a new
    version row. The notification delivery-gate fires only on approval.
    """

    tenant_id: uuid.UUID
    run_id: uuid.UUID
    employee_id: uuid.UUID
    employee_number: str
    employee_name: str
    gross: Money
    deductions: Money
    net: Money
    status: str = "draft"  # draft | approved | rejected
    version: int = 1
    rejected_reason: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    rejected_by: uuid.UUID | None = None
    rejected_at: datetime | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class PayrollEntry:
    """An immutable per-employee result row inside a payroll run.

    Once the run is approved, entries are frozen (no update, no delete).
    ``adjustments`` is free-form (bonus/other deductions) applied while the
    run is draft/computed.
    """

    tenant_id: uuid.UUID
    run_id: uuid.UUID
    employee_id: uuid.UUID
    base_salary: Money
    pay_days: int
    gross: Money
    deductions: Money
    net: Money
    adjustments: dict[str, object] | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class PayrollSettings:
    """Tenant payroll configuration - exactly one row per tenant."""

    tenant_id: uuid.UUID
    default_currency: str = "USD"
    pf_rate: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")
    rounding: PayrollRounding = PayrollRounding.NEAREST
    # HR-AUT-001 (0026): whether the tenant allows the payroll automation batch
    # engine to drive runs; pre-flight blocks a batch when this is off.
    ai_automation_enabled: bool = True
    # HR-AUT-001 (0029): whether marking a run paid also books the accrual JE
    # into the Finance inbox (off = fully manual flow).
    je_bridge_enabled: bool = True
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Finance entities (FIN-BE-002) - pure domain, no framework dependencies.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChartOfAccount:
    """One account in a tenant's chart of accounts (soft-deletable).

    ``code`` is unique per tenant and is the key the journal entry API accepts
    (``UNIQUE (tenant_id, code)``). Accounts referenced by history are never
    hard-deleted (composite FKs use RESTRICT); ``is_active`` is the removal path.
    """

    tenant_id: uuid.UUID
    code: str
    name: str
    account_type: AccountType
    is_active: bool = True
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class JournalLine:
    """One side of a double-entry journal transaction.

    Exactly one of ``debit`` / ``credit`` must be set (DB CHECK XOR), the amount
    must be non-zero and non-negative. Balance is NOT enforced here - drafts may
    be unbalanced; the service enforces balance only at ``post``.
    """

    account_id: uuid.UUID
    debit: Decimal | None = None
    credit: Decimal | None = None
    currency: str = "USD"
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class JournalEntry:
    """The header of one double-entry transaction.

    ``(source, source_ref)`` is the idempotency stamp: the DB ``UNIQUE (tenant_id,
    source, source_ref)`` means a replayed request (e.g. an invoice accrual) can
    never create a second entry. Manual entries use ``source_ref = None``.
    """

    tenant_id: uuid.UUID
    entry_date: date
    memo: str | None
    status: EntryStatus
    source: str
    source_ref: str | None
    lines: tuple[JournalLine, ...] = ()
    id: uuid.UUID | None = None
    posted_at: datetime | None = None
    posted_by_user_id: uuid.UUID | None = None
    voided_at: datetime | None = None
    reversal_entry_id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class InvoiceLine:
    """One line item of an invoice (``amount = quantity * unit_price``)."""

    invoice_id: uuid.UUID | None
    line_no: int
    description: str
    account_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    id: uuid.UUID | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class Invoice:
    """An accounts-receivable document (bill to a customer).

    Revenue is recognized only at ``approved`` (accrual). ``(source, source_ref)``
    is the idempotency stamp for ``InvoicePort.create_from_order`` (source =
    ``sales_order``); manual invoices default to source = ``manual`` with a NULL
    source_ref so unlimited manual bills stay allowed.
    """

    tenant_id: uuid.UUID
    invoice_number: str
    customer_id: uuid.UUID
    invoice_date: date
    due_date: date
    status: InvoiceStatus
    total: Decimal
    source: str
    source_ref: str | None
    lines: tuple[InvoiceLine, ...] = ()
    id: uuid.UUID | None = None
    issued_at: datetime | None = None
    approved_at: datetime | None = None
    voided_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Payment:
    """A cash receipt applied to an invoice (DR Cash / CR AR).

    ``(source, source_ref)`` is the second idempotency lock - a replayed
    ``apply_payment`` can never double-book.
    """

    tenant_id: uuid.UUID
    payment_number: str
    invoice_id: uuid.UUID
    amount: Decimal
    method: str
    paid_at: datetime
    status: PaymentStatus
    source: str
    source_ref: str | None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class FiscalPeriod:
    """An accounting period that can be closed to freeze history.

    An entry belongs to a period by ``entry_date`` range, not by FK; the
    closed-period gate compares dates.
    """

    tenant_id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_closed: bool = False
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Report read-models (derived from posted journal lines - never stored).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrialBalanceRow:
    account_id: uuid.UUID
    code: str
    name: str
    account_type: AccountType
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class TrialBalance:
    as_of: date
    rows: tuple[TrialBalanceRow, ...]
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True)
class PnlLine:
    account_id: uuid.UUID
    code: str
    name: str
    amount: Decimal


@dataclass(frozen=True)
class ProfitAndLoss:
    from_date: date
    to_date: date
    revenue: tuple[PnlLine, ...]
    expenses: tuple[PnlLine, ...]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


@dataclass(frozen=True)
class BalanceSheetLine:
    account_id: uuid.UUID
    code: str
    name: str
    balance: Decimal
    account_type: AccountType


@dataclass(frozen=True)
class BalanceSheet:
    as_of: date
    assets: tuple[BalanceSheetLine, ...]
    liabilities: tuple[BalanceSheetLine, ...]
    equity: tuple[BalanceSheetLine, ...]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal


@dataclass(frozen=True)
class ArAgingBucket:
    """One aging window of outstanding accounts receivable.

    ``bucket`` is one of ``current | 1_30 | 31_60 | 61_90 | over_90``; ``share``
    is the bucket's proportion of ``total_ar`` (0..1). Outstanding is derived
    from issued/approved (unpaid) invoices - fixed accounting columns do not
    track recoverability, so aging is a read-side derivation like the other
    reports.
    """

    bucket: str
    count: int
    amount: Decimal
    share: Decimal


@dataclass(frozen=True)
class ArAging:
    """Accounts-receivable aging read-model (derived from invoices, never stored)."""

    as_of: date
    total_ar: Decimal
    buckets: tuple[ArAgingBucket, ...]


# ---------------------------------------------------------------------------
# Finance automation read-models (SKY-56/SKY-64) - derived, never stored.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CloseChecklistItem:
    label: str
    status: str  # "ok" | "warning" | "missing"
    detail: str | None = None


@dataclass(frozen=True)
class CloseChecklist:
    period_id: uuid.UUID
    period_name: str
    items: tuple[CloseChecklistItem, ...]
    ready: bool


@dataclass(frozen=True)
class DuplicateCandidate:
    entry_id: uuid.UUID
    entry_date: date
    memo: str | None
    source_ref: str | None


@dataclass(frozen=True)
class DuplicateGroup:
    key: str
    reason: str
    entries: tuple[DuplicateCandidate, ...]


@dataclass(frozen=True)
class AnomalyItem:
    entity_type: str
    entity_id: uuid.UUID
    anomaly_type: str
    severity: str  # "low" | "medium" | "high"
    description: str
    detected_at: datetime


@dataclass(frozen=True)
class AnomalyReport:
    items: tuple[AnomalyItem, ...]


@dataclass(frozen=True)
class AccountCodeSuggestion:
    description: str
    suggested_code: str
    suggested_name: str
    confidence: Decimal
    reasoning: str = ""
    amount: Decimal | None = None
    side: str = "debit"
    contra_code: str = ""
    contra_name: str = ""


@dataclass(frozen=True)
class DraftEntryLine:
    account_code: str
    account_name: str
    amount: Decimal
    side: str  # "debit" or "credit"
    description: str = ""


@dataclass(frozen=True)
class DraftEntry:
    lines: tuple[DraftEntryLine, ...]
    explanation: str
    confidence: Decimal
    reasoning: str = ""
    model_used: str = ""


@dataclass(frozen=True)
class AnomalyNarration:
    narration: str
    model_used: str = ""


@dataclass(frozen=True)
class ReminderDraft:
    invoice_number: str
    customer_name: str | None = None
    amount: Decimal = Decimal("0")
    days_overdue: int = 0
    tone: str = "polite"
    subject: str = ""
    body: str = ""
    model_used: str = ""


@dataclass(frozen=True)
class WorkingCapitalAlert:
    ratio: Decimal
    threshold: Decimal
    current_assets: Decimal
    current_liabilities: Decimal
    alert: bool  # ratio < threshold


@dataclass(frozen=True)
class HealthComponent:
    name: str
    score: Decimal
    weight: Decimal
    detail: str | None = None


@dataclass(frozen=True)
class HealthScore:
    overall: Decimal
    components: tuple[HealthComponent, ...]


@dataclass(frozen=True)
class CashflowPosition:
    month: str  # "YYYY-MM"
    opening: Decimal
    inflows: Decimal
    outflows: Decimal
    closing: Decimal


@dataclass(frozen=True)
class CashflowProjection:
    positions: tuple[CashflowPosition, ...]


@dataclass(frozen=True)
class ComparativePnlRow:
    account_code: str
    account_name: str
    current_amount: Decimal
    prior_amount: Decimal
    variance: Decimal
    variance_pct: Decimal


@dataclass(frozen=True)
class ComparativePnl:
    current_from: date
    current_to: date
    prior_from: date
    prior_to: date
    rows: tuple[ComparativePnlRow, ...]


@dataclass(frozen=True)
class TenantSetting:
    """Generic tenant KV setting - row in erp_tenant_settings."""

    tenant_id: uuid.UUID
    key: str
    value: str
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AiFinanceAnomaly:
    """Persisted anomaly detected by automation - row in ai_finance_anomalies."""

    tenant_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    anomaly_type: str
    severity: str
    description: str
    status: str = "open"  # "open" | "reviewed" | "dismissed"
    id: uuid.UUID | None = None
    detected_at: datetime | None = None
    reviewed_at: datetime | None = None


@dataclass(frozen=True)
class AiFinanceSuggestion:
    """Persisted account-code suggestion - row in ai_finance_suggestions."""

    tenant_id: uuid.UUID
    description: str
    suggested_code: str
    suggested_name: str
    confidence: Decimal
    status: str = "pending"  # "pending" | "accepted" | "dismissed"
    id: uuid.UUID | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# CRM entities (leads, opportunities, customers) - CRM-DATA-001
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Lead:
    """An inbound inquiry before it has pipeline value.

    Owner/team-scoped: ``owner_id`` and ``team_id`` are plain UUID references
    to identity users (and a future teams model), resolved through ports at
    the service layer. ``email`` is deliberately not unique - dedupe is a
    soft probe at the service layer.
    """

    tenant_id: uuid.UUID
    status: LeadStatus = LeadStatus.NEW
    source: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Opportunity:
    """A pipeline deal - moves through stages and terminates won/lost.

    Deliberately customer-less in Phase 1 (a won opportunity is promoted to a
    customer by the service layer). ``amount`` is optional until the deal has
    value; when present it is a ``Money`` so the currency tag travels with it.
    ``won_at`` / ``lost_at`` are set exactly on the terminal transition.
    """

    tenant_id: uuid.UUID
    name: str
    lead_id: uuid.UUID | None = None
    stage: OpportunityStage = OpportunityStage.PROSPECTING
    amount: Money | None = None
    probability: int = 0
    expected_close_date: date | None = None
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    won_at: datetime | None = None
    lost_at: datetime | None = None
    lost_reason: str | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Customer:
    """An account we do business with.

    Soft-deleted via ``is_active`` (the ERP convention - no status enum).
    ``customer_code`` is the stable per-tenant external key. A NULL
    ``credit_limit`` means "no limit"; when present it is a ``Money`` so the
    currency tag travels with it.
    """

    tenant_id: uuid.UUID
    customer_code: str
    name: str
    source_opportunity_id: uuid.UUID | None = None
    email: str | None = None
    phone: str | None = None
    credit_limit: Money | None = None
    is_active: bool = True
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Contact:
    """A person on a customer account (a customer is the account).

    Tenant-scoped like its customer (customers have no owner/team columns -
    locked SKY-43 decision), soft-deleted via ``is_active``. ``customer_id``
    is a plain UUID anchor (no FK, mirroring ``source_opportunity_id``).
    """

    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None
    is_primary: bool = False
    is_active: bool = True
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Activity:
    """A unified CRM activity - task/call/meeting/follow-up/email/note.

    Owner/team-scoped (mirroring leads/opportunities): the repository applies
    the same OWNER/TEAM/ALL rule on ``owner_id``/``team_id``; rows created
    without an owner (e.g. customer-anchored notes) are tenant-visible.

    ``entity_type``/``entity_id`` anchor the activity to exactly one CRM
    entity. ``due_at`` marks task/follow-up deadlines; ``completed_at`` +
    ``completed_by`` are set together by the complete action.
    """

    tenant_id: uuid.UUID
    kind: ActivityKind
    entity_type: CrmEntityType
    entity_id: uuid.UUID
    subject: str
    description: str | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by: uuid.UUID | None = None
    notes: str | None = None
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Note:
    """A persistent free-form note on a CRM entity.

    Tenant-scoped; ``author_id`` records who wrote it. Anchored to exactly one
    CRM entity via ``entity_type``/``entity_id``.
    """

    tenant_id: uuid.UUID
    entity_type: CrmEntityType
    entity_id: uuid.UUID
    body: str
    author_id: uuid.UUID | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class TimelineEvent:
    """A curated CRM business event for the customer-facing timeline.

    Distinct from the security/compliance ``audit_logs`` trail and from the
    async ``crm.*`` domain events: this row IS the timeline record, written
    transactionally in the same request as the business action. Anchored to
    exactly one CRM entity (order creations anchor to the customer).
    """

    tenant_id: uuid.UUID
    entity_type: CrmEntityType
    entity_id: uuid.UUID
    event_type: CrmTimelineEventType
    title: str
    actor_id: uuid.UUID | None = None
    payload: dict[str, object] | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class TimelineItem:
    """One merged row of the customer-facing timeline (DB-layer UNION).

    Produced by the repository from activities + notes + timeline events -
    never assembled in application code from three independently paged lists.
    """

    source: str
    id: uuid.UUID
    tenant_id: uuid.UUID
    entity_type: CrmEntityType
    entity_id: uuid.UUID
    kind: str | None
    title: str | None
    body: str | None
    actor_id: uuid.UUID | None
    occurred_at: datetime


@dataclass(frozen=True)
class CrmSearchHit:
    """One server-side search match across the CRM entities."""

    tenant_id: uuid.UUID
    entity_type: CrmEntityType
    entity_id: uuid.UUID
    title: str
    subtitle: str | None = None


# ---------------------------------------------------------------------------
# Sales entities (orders, order lines) - CRM-DATA-001
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SalesOrder:
    """A customer commitment - the money record handed to finance.

    ``status`` follows ``draft -> confirmed -> fulfilled`` (``cancelled``
    terminal). The money columns are a cached projection: the service
    recomputes them from the lines on every write (CRM-BE-002) - never
    trusted from clients. ``credit_check`` records the confirm-time result.
    """

    tenant_id: uuid.UUID
    order_number: str
    customer_id: uuid.UUID
    status: OrderStatus = OrderStatus.DRAFT
    credit_check: CreditCheckResult = CreditCheckResult.PENDING
    subtotal: Money = field(default_factory=lambda: Money.zero("USD"))
    discount: Money = field(default_factory=lambda: Money.zero("USD"))
    tax: Money = field(default_factory=lambda: Money.zero("USD"))
    total: Money = field(default_factory=lambda: Money.zero("USD"))
    confirmed_at: datetime | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class SalesOrderLine:
    """One line of a sales order.

    ``product_name`` / ``sku`` are denormalized snapshots taken at order time
    so history stays stable even if the product catalog changes. Per-line
    prices are plain Decimals (the currency lives on the order header);
    ``line_total`` is a cached projection recomputed by the service.

    ``order_id`` is None on a line being created (the repository stamps the
    generated header id on write - mirroring ``InvoiceLine.invoice_id``) and
    always populated on read.
    """

    tenant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    quantity: Decimal
    order_id: uuid.UUID | None = None
    unit_price: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    line_total: Decimal = Decimal("0")
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class DeadStockItem:
    """A product with stock on hand but no outbound movement in the window.

    Valuation is server-side only at ``cost_price`` (INV-ANL-001): the HTTP
    layer must gate the ``tied_up_value`` / ``cost`` figures behind the
    ``erp.inventory.cost`` permission. ``qty_on_hand`` is the current
    materialized level for the product across its warehouse.
    """

    tenant_id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    name: str
    warehouse_id: uuid.UUID | None = None
    qty_on_hand: Decimal = Decimal("0")
    cost_price: Money = field(default_factory=lambda: Money.zero("USD"))
    tied_up_value: Money = field(default_factory=lambda: Money.zero("USD"))
    last_outbound_at: datetime | None = None
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class SlowMoverItem:
    """A bottom-quartile turnover item with a suggested-markdown advice flag.

    ``turnover_ratio`` is outbound qty in the trailing window divided by the
    current on-hand quantity (clamped to at least 1 to avoid division by
    zero). ``suggest_markdown`` is advice only — it NEVER triggers a price
    change (INV-ANL-001 guardrail).
    """

    tenant_id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    name: str
    warehouse_id: uuid.UUID | None = None
    qty_on_hand: Decimal = Decimal("0")
    turnover_ratio: Decimal = Decimal("0")
    cost_price: Money = field(default_factory=lambda: Money.zero("USD"))
    carrying_cost: Money = field(default_factory=lambda: Money.zero("USD"))
    last_outbound_at: datetime | None = None
    suggest_markdown: bool = False
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class MovementTrendPoint:
    """One week's stacked movement totals per warehouse (receipts/issues/adjustments).

    ``receipts`` / ``issues`` are stored as positive magnitudes for charting;
    ``issues`` represents outbound volume (positive). ``adjustments`` is the
    net adjustment quantity (may be negative).
    """

    tenant_id: uuid.UUID
    period_start: datetime
    warehouse_id: uuid.UUID | None = None
    receipts: Decimal = Decimal("0")
    issues: Decimal = Decimal("0")
    adjustments: Decimal = Decimal("0")


@dataclass(frozen=True)
class StockHealthSummary:
    """Aggregate stock-health metrics consumed by the SKY-63 narrator digest."""

    tenant_id: uuid.UUID
    total_sku_count: int = 0
    low_stock_count: int = 0
    dead_stock_count: int = 0
    slow_mover_count: int = 0
    tied_up_capital: Money = field(default_factory=lambda: Money.zero("USD"))


# ---------------------------------------------------------------------------
# Finance automation wave-2 read-models (SKY-66) - derived, never stored.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RevenueConcentrationEntry:
    """One customer's share of recognized revenue over a period (B11)."""

    customer_id: uuid.UUID
    customer_name: str | None
    amount: Decimal
    share: Decimal  # 0..1 of total revenue
    above_threshold: bool  # share >= threshold


@dataclass(frozen=True)
class RevenueConcentration:
    """Revenue concentration report - how dependent revenue is on top customers."""

    from_date: date
    to_date: date
    threshold: Decimal  # e.g. 0.25
    total_revenue: Decimal
    entries: tuple[RevenueConcentrationEntry, ...]


@dataclass(frozen=True)
class WorkingCapitalPosition:
    """Assets minus liabilities for a single month end (B12)."""

    month: str  # "YYYY-MM"
    assets: Decimal
    liabilities: Decimal
    working_capital: Decimal


@dataclass(frozen=True)
class WorkingCapitalSeries:
    """Monthly assets - liabilities trend (B12)."""

    positions: tuple[WorkingCapitalPosition, ...]


@dataclass(frozen=True)
class PaymentMethodAnalyticsEntry:
    """Revenue share by payment method over a period (B20)."""

    method: str
    count: int
    amount: Decimal
    share: Decimal  # 0..1 of total


@dataclass(frozen=True)
class PaymentMethodAnalytics:
    """How payments split by method - used to spot CPP/fee-heavy channels."""

    from_date: date
    to_date: date
    total_amount: Decimal
    entries: tuple[PaymentMethodAnalyticsEntry, ...]


@dataclass(frozen=True)
class AuditReadinessCheck:
    """A single audit-readiness gate and whether the tenant passes it (B32)."""

    key: str
    label: str
    status: str  # "ok" | "warning" | "missing"
    detail: str | None = None


@dataclass(frozen=True)
class AuditReadiness:
    """Overall audit-readiness posture for the tenant (B32)."""

    ready: bool
    checks: tuple[AuditReadinessCheck, ...]
