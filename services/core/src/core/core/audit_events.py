"""Canonical audit event keys for the core (ERP) domain.

Single source of truth for the free-form ``action`` strings written to the
core audit trails - ``core_audit_logs`` (HR/payroll, see ``core.core.
audit_service``) and ``audit_logs`` (the shared ``features.audit`` trail used
by finance/inventory). Services must reference these constants instead of
hardcoding strings so the event vocabulary stays greppable and drift-checked
against the catalog grouping below.

Vocabulary is defined by the HR & Payroll design doc (``docs/modules/
hr-payroll.md``, step 4) and the finance/inventory modules - ``{domain}.
{entity}.{action}``, e.g. ``hr.leave.approved``, ``finance.invoice.issued``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# HR
# ---------------------------------------------------------------------------
HR_DEPARTMENT_CREATED = "hr.department.created"
HR_DEPARTMENT_UPDATED = "hr.department.updated"
HR_EMPLOYEE_CREATED = "hr.employee.created"
HR_EMPLOYEE_UPDATED = "hr.employee.updated"
HR_EMPLOYEE_TERMINATED = "hr.employee.terminated"
HR_LEAVE_REQUESTED = "hr.leave.requested"
HR_LEAVE_APPROVED = "hr.leave.approved"
HR_LEAVE_REJECTED = "hr.leave.rejected"
HR_LEAVE_CANCELLED = "hr.leave.cancelled"
HR_LEAVE_BALANCE_ADJUSTED = "hr.leave.balance.adjusted"
HR_LEAVE_ACCRUED = "hr.leave.accrued"
HR_LEAVE_POLICY_UPDATED = "hr.leave.policy.updated"
HR_ATTENDANCE_RECORDED = "hr.attendance.recorded"
HR_AI_RISK_ACKNOWLEDGED = "hr.ai.risk.acknowledged"
HR_AI_ANOMALY_ACKNOWLEDGED = "hr.ai.anomaly.acknowledged"
HR_AI_ANOMALY_DISMISSED = "hr.ai.anomaly.dismissed"
HR_AI_ANOMALY_RESOLVED = "hr.ai.anomaly.resolved"
HR_AI_COMPLIANCE_ACKNOWLEDGED = "hr.ai.compliance.acknowledged"
HR_AI_COMPLIANCE_RESOLVED = "hr.ai.compliance.resolved"
# HR-AI-003: L3 analytics narrative generation (every access audited, aggregates only).
HR_AI_L3_PAYROLL_COST_NARRATED = "hr.ai.l3.payroll_cost.narrated"
HR_AI_L3_LEAVE_PAY_CORRELATED = "hr.ai.l3.leave_pay.correlated"
HR_AI_L3_COMPLIANCE_DIGESTED = "hr.ai.l3.compliance.digested"

# ---------------------------------------------------------------------------
# Payroll
# ---------------------------------------------------------------------------
PAYROLL_RUN_CREATED = "payroll.run.created"
PAYROLL_RUN_COMPUTED = "payroll.run.computed"
PAYROLL_RUN_APPROVED = "payroll.run.approved"
PAYROLL_RUN_PAID = "payroll.run.paid"
PAYROLL_RUN_VOIDED = "payroll.run.voided"
PAYROLL_ENTRY_ADJUSTED = "payroll.entry.adjusted"
PAYROLL_SETTINGS_UPDATED = "payroll.settings.updated"
PAYROLL_COMPENSATION_RECORDED = "payroll.compensation.recorded"
PAYROLL_AUTO_NOTIFICATIONS_SENT = "payroll.automation.notifications.sent"
PAYROLL_AUTO_SCHEDULE_CREATED = "payroll.automation.schedule.created"
PAYROLL_AUTO_SCHEDULE_UPDATED = "payroll.automation.schedule.updated"
PAYROLL_AUTO_SCHEDULE_DELETED = "payroll.automation.schedule.deleted"
PAYROLL_AUTO_SCHEDULE_FIRED = "payroll.automation.schedule.fired"
# 0030: per-payslip review lifecycle (draft -> approved | rejected).
PAYROLL_PAYSLIP_APPROVED = "payroll.payslip.approved"
PAYROLL_PAYSLIP_REJECTED = "payroll.payslip.rejected"

# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------
FINANCE_CHART_OF_ACCOUNTS_CREATED = "finance.chart_of_accounts.created"
FINANCE_CHART_OF_ACCOUNTS_DEACTIVATED = "finance.chart_of_accounts.deactivated"
FINANCE_JOURNAL_ENTRY_POSTED = "finance.journal_entry.posted"
FINANCE_JOURNAL_ENTRY_VOIDED = "finance.journal_entry.voided"
FINANCE_FISCAL_PERIOD_CREATED = "finance.fiscal_period.created"
FINANCE_FISCAL_PERIOD_CLOSED = "finance.fiscal_period.closed"
FINANCE_INVOICE_CREATED = "finance.invoice.created"
FINANCE_INVOICE_ISSUED = "finance.invoice.issued"
FINANCE_INVOICE_APPROVED = "finance.invoice.approved"
FINANCE_INVOICE_VOIDED = "finance.invoice.voided"
FINANCE_PAYMENT_APPLIED = "finance.payment.applied"
FINANCE_JOURNAL_ENTRY_REVERSED = "finance.journal_entry.reversed"
FINANCE_ANOMALY_DETECTED = "finance.anomaly.detected"
FINANCE_DUPLICATE_SUGGESTION_CREATED = "finance.suggestion.duplicate.created"
FINANCE_AI_SUGGESTION_GENERATED = "finance.ai.suggestion.generated"
FINANCE_AI_DRAFT_GENERATED = "finance.ai.draft.generated"
FINANCE_AI_DRAFT_APPLIED = "finance.ai.draft.applied"
FINANCE_AI_ANOMALY_NARRATED = "finance.ai.anomaly.narrated"
FINANCE_AI_REMINDER_GENERATED = "finance.ai.reminder.generated"

# ---------------------------------------------------------------------------
# Reports (RPT-BE-001)
# ---------------------------------------------------------------------------
REPORT_EXPORTED = "report.exported"
# RPT-AI-001 (SKY-80): a generated report spec was persisted as a new
# erp_report_definitions row via POST /api/v1/reports.
REPORT_CREATED = "report.created"

# Every catalogued audit event, in catalog order.
CATALOG: tuple[str, ...] = (
    HR_DEPARTMENT_CREATED,
    HR_DEPARTMENT_UPDATED,
    HR_EMPLOYEE_CREATED,
    HR_EMPLOYEE_UPDATED,
    HR_EMPLOYEE_TERMINATED,
    HR_LEAVE_REQUESTED,
    HR_LEAVE_APPROVED,
    HR_LEAVE_REJECTED,
    HR_LEAVE_CANCELLED,
    HR_LEAVE_BALANCE_ADJUSTED,
    HR_LEAVE_ACCRUED,
    HR_LEAVE_POLICY_UPDATED,
    HR_ATTENDANCE_RECORDED,
    HR_AI_RISK_ACKNOWLEDGED,
    HR_AI_ANOMALY_ACKNOWLEDGED,
    HR_AI_ANOMALY_DISMISSED,
    HR_AI_ANOMALY_RESOLVED,
    HR_AI_COMPLIANCE_ACKNOWLEDGED,
    HR_AI_COMPLIANCE_RESOLVED,
    HR_AI_L3_PAYROLL_COST_NARRATED,
    HR_AI_L3_LEAVE_PAY_CORRELATED,
    HR_AI_L3_COMPLIANCE_DIGESTED,
    PAYROLL_RUN_CREATED,
    PAYROLL_RUN_COMPUTED,
    PAYROLL_RUN_APPROVED,
    PAYROLL_RUN_PAID,
    PAYROLL_RUN_VOIDED,
    PAYROLL_ENTRY_ADJUSTED,
    PAYROLL_SETTINGS_UPDATED,
    PAYROLL_COMPENSATION_RECORDED,
    PAYROLL_PAYSLIP_APPROVED,
    PAYROLL_PAYSLIP_REJECTED,
    PAYROLL_AUTO_NOTIFICATIONS_SENT,
    PAYROLL_AUTO_SCHEDULE_CREATED,
    PAYROLL_AUTO_SCHEDULE_UPDATED,
    PAYROLL_AUTO_SCHEDULE_DELETED,
    PAYROLL_AUTO_SCHEDULE_FIRED,
    FINANCE_CHART_OF_ACCOUNTS_CREATED,
    FINANCE_CHART_OF_ACCOUNTS_DEACTIVATED,
    FINANCE_JOURNAL_ENTRY_POSTED,
    FINANCE_JOURNAL_ENTRY_VOIDED,
    FINANCE_JOURNAL_ENTRY_REVERSED,
    FINANCE_ANOMALY_DETECTED,
    FINANCE_DUPLICATE_SUGGESTION_CREATED,
    FINANCE_FISCAL_PERIOD_CREATED,
    FINANCE_FISCAL_PERIOD_CLOSED,
    FINANCE_INVOICE_CREATED,
    FINANCE_INVOICE_ISSUED,
    FINANCE_INVOICE_APPROVED,
    FINANCE_INVOICE_VOIDED,
    FINANCE_PAYMENT_APPLIED,
    FINANCE_AI_SUGGESTION_GENERATED,
    FINANCE_AI_DRAFT_GENERATED,
    FINANCE_AI_DRAFT_APPLIED,
    FINANCE_AI_ANOMALY_NARRATED,
    FINANCE_AI_REMINDER_GENERATED,
    REPORT_EXPORTED,
    REPORT_CREATED,
)

ALL_AUDIT_EVENTS: frozenset[str] = frozenset(CATALOG)

# Event module groupings (for catalog endpoints and UI).
# Each entry: (module_key, module_label, (event_keys, ...))
AUDIT_EVENT_MODULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "hr",
        "HR",
        (
            HR_DEPARTMENT_CREATED,
            HR_DEPARTMENT_UPDATED,
            HR_EMPLOYEE_CREATED,
            HR_EMPLOYEE_UPDATED,
            HR_EMPLOYEE_TERMINATED,
            HR_LEAVE_REQUESTED,
            HR_LEAVE_APPROVED,
            HR_LEAVE_REJECTED,
            HR_LEAVE_CANCELLED,
            HR_LEAVE_BALANCE_ADJUSTED,
            HR_LEAVE_ACCRUED,
            HR_LEAVE_POLICY_UPDATED,
            HR_ATTENDANCE_RECORDED,
            HR_AI_RISK_ACKNOWLEDGED,
            HR_AI_ANOMALY_ACKNOWLEDGED,
            HR_AI_ANOMALY_DISMISSED,
            HR_AI_ANOMALY_RESOLVED,
            HR_AI_COMPLIANCE_ACKNOWLEDGED,
            HR_AI_COMPLIANCE_RESOLVED,
            HR_AI_L3_PAYROLL_COST_NARRATED,
            HR_AI_L3_LEAVE_PAY_CORRELATED,
            HR_AI_L3_COMPLIANCE_DIGESTED,
        ),
    ),
    (
        "payroll",
        "Payroll",
        (
            PAYROLL_RUN_CREATED,
            PAYROLL_RUN_COMPUTED,
            PAYROLL_RUN_APPROVED,
            PAYROLL_RUN_PAID,
            PAYROLL_RUN_VOIDED,
            PAYROLL_ENTRY_ADJUSTED,
            PAYROLL_SETTINGS_UPDATED,
            PAYROLL_COMPENSATION_RECORDED,
            PAYROLL_AUTO_NOTIFICATIONS_SENT,
            PAYROLL_AUTO_SCHEDULE_CREATED,
            PAYROLL_AUTO_SCHEDULE_UPDATED,
            PAYROLL_AUTO_SCHEDULE_DELETED,
            PAYROLL_AUTO_SCHEDULE_FIRED,
            PAYROLL_PAYSLIP_APPROVED,
            PAYROLL_PAYSLIP_REJECTED,
        ),
    ),
    (
        "finance",
        "Finance",
        (
            FINANCE_CHART_OF_ACCOUNTS_CREATED,
            FINANCE_CHART_OF_ACCOUNTS_DEACTIVATED,
            FINANCE_JOURNAL_ENTRY_POSTED,
            FINANCE_JOURNAL_ENTRY_VOIDED,
            FINANCE_JOURNAL_ENTRY_REVERSED,
            FINANCE_FISCAL_PERIOD_CREATED,
            FINANCE_FISCAL_PERIOD_CLOSED,
            FINANCE_INVOICE_CREATED,
            FINANCE_INVOICE_ISSUED,
            FINANCE_INVOICE_APPROVED,
            FINANCE_INVOICE_VOIDED,
            FINANCE_PAYMENT_APPLIED,
            FINANCE_ANOMALY_DETECTED,
            FINANCE_DUPLICATE_SUGGESTION_CREATED,
            FINANCE_AI_SUGGESTION_GENERATED,
            FINANCE_AI_DRAFT_GENERATED,
            FINANCE_AI_DRAFT_APPLIED,
            FINANCE_AI_ANOMALY_NARRATED,
            FINANCE_AI_REMINDER_GENERATED,
        ),
    ),
    (
        "reports",
        "Reports",
        (REPORT_EXPORTED, REPORT_CREATED),
    ),
)


def _assert_catalog_union() -> None:
    """Ensure AUDIT_EVENT_MODULES and CATALOG stay in sync (fail-fast on drift)."""
    module_keys = {key for _, _, keys in AUDIT_EVENT_MODULES for key in keys}
    if module_keys != ALL_AUDIT_EVENTS:
        missing = ALL_AUDIT_EVENTS - module_keys
        orphaned = module_keys - ALL_AUDIT_EVENTS
        msg = "AUDIT_EVENT_MODULES <-> CATALOG mismatch:\n"
        if missing:
            msg += f"  Missing from AUDIT_EVENT_MODULES: {sorted(missing)}\n"
        if orphaned:
            msg += f"  Orphaned in AUDIT_EVENT_MODULES: {sorted(orphaned)}\n"
        raise ValueError(msg)


_assert_catalog_union()

__all__ = [
    "ALL_AUDIT_EVENTS",
    "AUDIT_EVENT_MODULES",
    "CATALOG",
    "FINANCE_AI_ANOMALY_NARRATED",
    "FINANCE_AI_DRAFT_APPLIED",
    "FINANCE_AI_DRAFT_GENERATED",
    "FINANCE_AI_REMINDER_GENERATED",
    "FINANCE_AI_SUGGESTION_GENERATED",
    "FINANCE_ANOMALY_DETECTED",
    "FINANCE_CHART_OF_ACCOUNTS_CREATED",
    "FINANCE_CHART_OF_ACCOUNTS_DEACTIVATED",
    "FINANCE_DUPLICATE_SUGGESTION_CREATED",
    "FINANCE_FISCAL_PERIOD_CLOSED",
    "FINANCE_FISCAL_PERIOD_CREATED",
    "FINANCE_INVOICE_APPROVED",
    "FINANCE_INVOICE_CREATED",
    "FINANCE_INVOICE_ISSUED",
    "FINANCE_INVOICE_VOIDED",
    "FINANCE_JOURNAL_ENTRY_POSTED",
    "FINANCE_JOURNAL_ENTRY_REVERSED",
    "FINANCE_JOURNAL_ENTRY_VOIDED",
    "FINANCE_PAYMENT_APPLIED",
    "HR_AI_ANOMALY_ACKNOWLEDGED",
    "HR_AI_ANOMALY_DISMISSED",
    "HR_AI_ANOMALY_RESOLVED",
    "HR_AI_COMPLIANCE_ACKNOWLEDGED",
    "HR_AI_COMPLIANCE_RESOLVED",
    "HR_AI_L3_COMPLIANCE_DIGESTED",
    "HR_AI_L3_LEAVE_PAY_CORRELATED",
    "HR_AI_L3_PAYROLL_COST_NARRATED",
    "HR_AI_RISK_ACKNOWLEDGED",
    "HR_DEPARTMENT_CREATED",
    "HR_DEPARTMENT_UPDATED",
    "HR_EMPLOYEE_CREATED",
    "HR_EMPLOYEE_TERMINATED",
    "HR_EMPLOYEE_UPDATED",
    "HR_LEAVE_ACCRUED",
    "HR_LEAVE_APPROVED",
    "HR_LEAVE_BALANCE_ADJUSTED",
    "HR_LEAVE_CANCELLED",
    "HR_LEAVE_POLICY_UPDATED",
    "HR_LEAVE_REJECTED",
    "HR_LEAVE_REQUESTED",
    "PAYROLL_AUTO_NOTIFICATIONS_SENT",
    "PAYROLL_AUTO_SCHEDULE_CREATED",
    "PAYROLL_AUTO_SCHEDULE_DELETED",
    "PAYROLL_AUTO_SCHEDULE_FIRED",
    "PAYROLL_AUTO_SCHEDULE_UPDATED",
    "PAYROLL_COMPENSATION_RECORDED",
    "PAYROLL_ENTRY_ADJUSTED",
    "PAYROLL_PAYSLIP_APPROVED",
    "PAYROLL_PAYSLIP_REJECTED",
    "PAYROLL_RUN_APPROVED",
    "PAYROLL_RUN_COMPUTED",
    "PAYROLL_RUN_CREATED",
    "PAYROLL_RUN_PAID",
    "PAYROLL_RUN_VOIDED",
    "PAYROLL_SETTINGS_UPDATED",
    "REPORT_CREATED",
    "REPORT_EXPORTED",
]
