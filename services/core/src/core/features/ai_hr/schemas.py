"""Pydantic response schemas for the L1 HR/Payroll AI endpoints.

Mirror the aggregate dataclasses from :mod:`core.features.ai_hr.repository`.
None of these models carries an employee identifier, name, or per-person value -
they are L1 shapes by construction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.features.ai_hr.anomaly_repository import LeaveAnomaly
from core.features.ai_hr.anomaly_service import AnomalyOrgSummary
from core.features.ai_hr.attrition_repository import ScoredRisk
from core.features.ai_hr.compliance_repository import ComplianceFindingRow
from core.features.ai_hr.compliance_service import ComplianceOrgSummary
from core.features.ai_hr.pattern_data_repository import LeaveBlackoutPeriod, PublicHoliday
from core.features.ai_hr.payroll_anomaly_repository import PayrollAnomaly
from core.features.ai_hr.payroll_anomaly_service import PayrollAnomalyOrgSummary
from core.features.ai_hr.quality_repository import EmployeeQuality
from core.features.ai_hr.quality_service import QualityOrgKpi
from core.features.ai_hr.repository import (
    DepartmentCount,
    HeadcountPoint,
    Overview,
    TenureBand,
    TenureSummary,
)
from core.features.ai_hr.suggestion_repository import LeaveSuggestion
from core.features.ai_hr.suggestion_service import SuggestionOrgSummary
from core.features.ai_hr.utilization_repository import UtilizationAlert
from core.features.ai_hr.utilization_service import UtilizationOrgSummary


class HeadcountPointOut(BaseModel):
    year: int
    month: int
    hires: int


class DepartmentCountOut(BaseModel):
    department_id: uuid.UUID | None
    department_name: str
    count: int


class TenureBandOut(BaseModel):
    band: str
    count: int


class OverviewOut(BaseModel):
    total_headcount: int
    trend: list[HeadcountPointOut]
    departments: list[DepartmentCountOut]
    tenure_bands: list[TenureBandOut]
    generated_at: datetime
    narrative: str


class TenureSummaryOut(BaseModel):
    total_headcount: int
    bands: list[TenureBandOut]
    generated_at: datetime
    narrative: str


def overview_to_out(overview: Overview) -> OverviewOut:
    return OverviewOut(
        total_headcount=overview.total_headcount,
        trend=[
            HeadcountPointOut(year=p.year, month=p.month, hires=p.hires) for p in overview.trend
        ],
        departments=[
            DepartmentCountOut(
                department_id=d.department_id,
                department_name=d.department_name,
                count=d.count,
            )
            for d in overview.departments
        ],
        tenure_bands=[TenureBandOut(band=b.band, count=b.count) for b in overview.tenure_bands],
        generated_at=overview.generated_at,
        narrative=overview.narrative,
    )


def tenure_to_out(summary: TenureSummary) -> TenureSummaryOut:
    return TenureSummaryOut(
        total_headcount=summary.total_headcount,
        bands=[TenureBandOut(band=b.band, count=b.count) for b in summary.bands],
        generated_at=summary.generated_at,
        narrative=summary.narrative,
    )


class FactorOut(BaseModel):
    feature: str
    contribution: float
    direction: str


class EmployeeRiskOut(BaseModel):
    """L2 individual risk - the ONLY shape allowed to carry a name/number."""

    employee_id: uuid.UUID
    employee_number: str | None
    name: str | None
    department_name: str | None
    risk_band: str
    score: float
    confidence: float
    factors: list[FactorOut]
    acknowledged: bool
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None


class AttritionDetailOut(BaseModel):
    """L2 response for callers holding ``erp.hr.ai.individual``."""

    generated_at: datetime
    model_version: str
    employees: list[EmployeeRiskOut]


class DepartmentRiskOut(BaseModel):
    department_name: str
    high_risk_count: int
    total_scores: int
    average_risk: float


class AttritionSummaryOut(BaseModel):
    """L1 aggregate response - never carries an employee identifier/name."""

    generated_at: datetime
    model_version: str
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    top_risk_departments: list[DepartmentRiskOut]
    narrative: str


def attrition_l2_to_out(scored: Sequence[ScoredRisk]) -> AttritionDetailOut:
    employees = [
        EmployeeRiskOut(
            employee_id=s.employee_id,
            employee_number=s.employee_number,
            name=f"{s.first_name or ''} {s.last_name or ''}".strip() or None,
            department_name=s.department_name,
            risk_band=s.risk_band,
            score=s.score,
            confidence=s.confidence,
            factors=[FactorOut(**f) for f in s.factors],
            acknowledged=s.acknowledged,
            acknowledged_by=s.acknowledged_by,
            acknowledged_at=s.acknowledged_at,
        )
        for s in scored
    ]
    return AttritionDetailOut(
        generated_at=scored[0].generated_at if scored else datetime.now(),
        model_version=scored[0].model_version if scored else "",
        employees=employees,
    )


def attrition_l1_to_out(scored: Sequence[ScoredRisk]) -> AttritionSummaryOut:
    by_band = {"high": 0, "medium": 0, "low": 0}
    dept: dict[str, list[float]] = {}
    for s in scored:
        by_band[s.risk_band] = by_band.get(s.risk_band, 0) + 1
        dept.setdefault(s.department_name or "Unassigned", []).append(s.score)
    top_departments = sorted(
        (
            DepartmentRiskOut(
                department_name=name,
                high_risk_count=sum(
                    1
                    for s in scored
                    if (s.department_name or "Unassigned") == name and s.risk_band == "high"
                ),
                total_scores=len(scores),
                average_risk=round(sum(scores) / len(scores), 4),
            )
            for name, scores in dept.items()
        ),
        key=lambda d: (d.high_risk_count, d.average_risk),
        reverse=True,
    )[:5]
    narrative = (
        f"{by_band['high']} employee(s) at high attrition risk, "
        f"{by_band['medium']} medium, {by_band['low']} low."
    )
    if top_departments:
        top = top_departments[0]
        narrative += f" Highest-risk team is {top.department_name}."
    return AttritionSummaryOut(
        generated_at=scored[0].generated_at if scored else datetime.now(),
        model_version=scored[0].model_version if scored else "",
        high_risk_count=by_band["high"],
        medium_risk_count=by_band["medium"],
        low_risk_count=by_band["low"],
        top_risk_departments=top_departments,
        narrative=narrative,
    )


class DepartmentQualityOut(BaseModel):
    department_name: str
    average_score: float
    low_quality_count: int
    scored: int


class QualityOrgOut(BaseModel):
    """L1 aggregate response - never carries an employee identifier/name."""

    total_scored: int
    average_score: float
    grade_distribution: dict[str, int]
    department_averages: list[DepartmentQualityOut]
    generated_at: datetime
    narrative: str


class EmployeeQualityOut(BaseModel):
    """L2 individual quality - the ONLY shape allowed to carry name/number."""

    employee_id: uuid.UUID
    employee_number: str | None
    name: str | None
    department_name: str | None
    score: float
    grade: str
    mandatory_score: float
    contact_score: float
    document_score: float
    issues: dict[str, list[str]]
    generated_at: datetime


def quality_org_to_out(kpi: QualityOrgKpi) -> QualityOrgOut:
    return QualityOrgOut(
        total_scored=kpi.total_scored,
        average_score=kpi.average_score,
        grade_distribution=kpi.grade_distribution,
        department_averages=[
            DepartmentQualityOut(
                department_name=d.department_name,
                average_score=d.average_score,
                low_quality_count=d.low_quality_count,
                scored=d.scored,
            )
            for d in kpi.department_averages
        ],
        generated_at=kpi.generated_at,
        narrative=kpi.narrative,
    )


def employee_quality_to_out(q: EmployeeQuality) -> EmployeeQualityOut:
    return EmployeeQualityOut(
        employee_id=q.employee_id,
        employee_number=q.employee_number,
        name=f"{q.first_name or ''} {q.last_name or ''}".strip() or None,
        department_name=q.department_name,
        score=q.score,
        grade=q.grade,
        mandatory_score=q.mandatory_score,
        contact_score=q.contact_score,
        document_score=q.document_score,
        issues={
            "mandatory": q.mandatory_missing,
            "contact": q.contact_issues,
            "document": q.document_issues,
        },
        generated_at=q.generated_at,
    )


class QualityRefreshOut(BaseModel):
    """Result of a forced data-quality recompute (L1 maintenance op)."""

    recount: int
    generated_at: datetime


class UtilizationAlertOut(BaseModel):
    """One utilization finding (L2 / self-scoped feed)."""

    employee_id: uuid.UUID
    employee_number: str | None
    name: str | None
    department_name: str | None
    alert_type: str
    severity: str
    balance_days: int
    projected_forfeiture_days: int | None
    days_remaining_in_year: int | None
    leave_type: str | None
    status: str | None
    evidence: dict[str, Any]
    created_at: datetime


class UtilizationOrgOut(BaseModel):
    """L1 aggregate response - never carries an employee identifier/name."""

    total_alerts: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    generated_at: datetime
    narrative: str


def utilization_alert_to_out(a: UtilizationAlert) -> UtilizationAlertOut:
    return UtilizationAlertOut(
        employee_id=a.employee_id,
        employee_number=a.employee_number,
        name=f"{a.first_name or ''} {a.last_name or ''}".strip() or None,
        department_name=a.department_name,
        alert_type=a.alert_type,
        severity=a.severity,
        balance_days=a.balance_days,
        projected_forfeiture_days=a.projected_forfeiture_days,
        days_remaining_in_year=a.days_remaining_in_year,
        leave_type=a.leave_type,
        status=a.status,
        evidence=a.evidence,
        created_at=a.created_at,
    )


def utilization_org_to_out(summary: UtilizationOrgSummary) -> UtilizationOrgOut:
    return UtilizationOrgOut(
        total_alerts=summary.total_alerts,
        by_type=summary.by_type,
        by_severity=summary.by_severity,
        generated_at=summary.generated_at,
        narrative=summary.narrative,
    )


class LeaveAnomalyOut(BaseModel):
    """One leave-pattern finding (L2 / self-scoped feed)."""

    employee_id: uuid.UUID
    employee_number: str | None
    name: str | None
    department_name: str | None
    anomaly_type: str
    severity: str
    title: str
    description: str
    team_size: int
    evidence: dict[str, Any]
    status: str | None
    created_at: datetime


class AnomalyOrgOut(BaseModel):
    """L1 aggregate response - never carries an employee identifier/name."""

    total_anomalies: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    generated_at: datetime
    narrative: str


def anomaly_to_out(a: LeaveAnomaly) -> LeaveAnomalyOut:
    return LeaveAnomalyOut(
        employee_id=a.employee_id,
        employee_number=a.employee_number,
        name=f"{a.first_name or ''} {a.last_name or ''}".strip() or None,
        department_name=a.department_name,
        anomaly_type=a.anomaly_type,
        severity=a.severity,
        title=a.title,
        description=a.description,
        team_size=a.team_size,
        evidence=a.evidence,
        status=a.status,
        created_at=a.created_at,
    )


def anomaly_org_to_out(summary: AnomalyOrgSummary) -> AnomalyOrgOut:
    return AnomalyOrgOut(
        total_anomalies=summary.total_anomalies,
        by_type=summary.by_type,
        by_severity=summary.by_severity,
        generated_at=summary.generated_at,
        narrative=summary.narrative,
    )


class LeaveSuggestionOut(BaseModel):
    """One suggested leave window (L2 / self-scoped feed)."""

    suggestion_id: uuid.UUID | None
    employee_id: uuid.UUID
    employee_number: str | None
    name: str | None
    department_name: str | None
    leave_type: str
    start_date: date
    end_date: date
    days: int
    reasons: list[str]
    status: str
    used_at: datetime | None
    created_at: datetime


class SuggestionOrgOut(BaseModel):
    """L1 aggregate response - never carries an employee identifier/name."""

    total_suggestions: int
    pending: int
    by_leave_type: dict[str, int]
    generated_at: datetime
    narrative: str


def suggestion_to_out(s: LeaveSuggestion) -> LeaveSuggestionOut:
    return LeaveSuggestionOut(
        suggestion_id=s.suggestion_id,
        employee_id=s.employee_id,
        employee_number=s.employee_number,
        name=f"{s.first_name or ''} {s.last_name or ''}".strip() or None,
        department_name=s.department_name,
        leave_type=s.leave_type,
        start_date=s.start_date,
        end_date=s.end_date,
        days=s.days,
        reasons=s.reasons,
        status=s.status,
        used_at=s.used_at,
        created_at=s.created_at,
    )


def suggestion_org_to_out(summary: SuggestionOrgSummary) -> SuggestionOrgOut:
    return SuggestionOrgOut(
        total_suggestions=summary.total_suggestions,
        pending=summary.pending,
        by_leave_type=summary.by_leave_type,
        generated_at=summary.generated_at,
        narrative=summary.narrative,
    )


class HrEvalRunWrite(BaseModel):
    """One precision metric recorded by the ai-agent eval harness (SKY-72)."""

    model_name: str = Field(min_length=1, max_length=64)
    metric: str = Field(min_length=1, max_length=32)
    precision: float = Field(ge=0.0, le=1.0)
    considered: int = Field(ge=0)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    met_threshold: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HrEvalWriteOut(BaseModel):
    """Confirmation of one batch of recorded eval metrics."""

    recorded: int


class PublicHolidayWrite(BaseModel):
    """Define one public-holiday / office-closure day (8.2.1 input config)."""

    calendar_date: date
    name: str = Field(min_length=1, max_length=100)
    department_id: uuid.UUID | None = None


class PublicHolidayOut(BaseModel):
    """One stored holiday row."""

    holiday_id: uuid.UUID
    calendar_date: date
    name: str
    department_id: uuid.UUID | None
    created_at: datetime


class LeaveBlackoutWrite(BaseModel):
    """Define one leave-blackout window (8.2.4 input config)."""

    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=200)
    department_id: uuid.UUID | None = None


class LeaveBlackoutOut(BaseModel):
    """One stored blackout window."""

    blackout_id: uuid.UUID
    start_date: date
    end_date: date
    department_id: uuid.UUID | None
    reason: str
    created_at: datetime


def public_holiday_to_out(h: PublicHoliday) -> PublicHolidayOut:
    return PublicHolidayOut(
        holiday_id=h.holiday_id,
        calendar_date=h.calendar_date,
        name=h.name,
        department_id=h.department_id,
        created_at=h.created_at,
    )


def leave_blackout_to_out(b: LeaveBlackoutPeriod) -> LeaveBlackoutOut:
    return LeaveBlackoutOut(
        blackout_id=b.blackout_id,
        start_date=b.start_date,
        end_date=b.end_date,
        department_id=b.department_id,
        reason=b.reason,
        created_at=b.created_at,
    )


class PayrollAnomalyOut(BaseModel):
    """One payroll finding (L2 / individual drill-down).

    ``employee_id``/``employee_number``/``name`` are nullable: the
    ``duplicate_account`` type spans several employees and is anchored to one
    primary subject; per the storage convention the finding's ``title`` and
    ``description`` live under the ``evidence`` keys of the same name and are
    surfaced here as first-class fields.
    """

    anomaly_id: uuid.UUID
    run_id: uuid.UUID
    run_code: str | None
    period_start: date | None
    period_end: date | None
    employee_id: uuid.UUID | None
    employee_number: str | None
    name: str | None
    department_name: str | None
    anomaly_type: str
    severity: str
    title: str
    description: str
    evidence: dict[str, Any]
    status: str
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    created_at: datetime


class PayrollAnomalyOrgOut(BaseModel):
    """L1 aggregate response — never carries an employee identifier/name."""

    total_anomalies: int
    open_anomalies: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    generated_at: datetime
    narrative: str


class PayrollAnomalyDispositionWrite(BaseModel):
    """Body for a disposition POST (``erp.hr.ai.acknowledge``)."""

    status: str = Field(pattern="^(acknowledged|dismissed|resolved)$")


def payroll_anomaly_to_out(a: PayrollAnomaly) -> PayrollAnomalyOut:
    return PayrollAnomalyOut(
        anomaly_id=a.anomaly_id,  # type: ignore[arg-type]  # DB PK is always present at runtime
        run_id=a.run_id,
        run_code=a.run_code,
        period_start=a.period_start,
        period_end=a.period_end,
        employee_id=a.employee_id,
        employee_number=a.employee_number,
        name=f"{a.first_name or ''} {a.last_name or ''}".strip() or None,
        department_name=a.department_name,
        anomaly_type=a.anomaly_type,
        severity=a.severity,
        title=a.title,
        description=a.description,
        evidence=a.evidence,
        status=a.status,
        acknowledged_by=a.acknowledged_by,
        acknowledged_at=a.acknowledged_at,
        created_at=a.created_at,
    )


def payroll_anomaly_org_to_out(summary: PayrollAnomalyOrgSummary) -> PayrollAnomalyOrgOut:
    return PayrollAnomalyOrgOut(
        total_anomalies=summary.total_anomalies,
        open_anomalies=summary.open_anomalies,
        by_type=summary.by_type,
        by_severity=summary.by_severity,
        generated_at=summary.generated_at,
        narrative=summary.narrative,
    )


class ComplianceFindingOut(BaseModel):
    """One compliance finding (L2 / individual drill-down).

    ``employee_id``/``employee_number``/``name`` are nullable (tenant-level
    findings anchor to no single person). ``title``/``description`` live under
    the ``evidence`` keys of the same name and are surfaced here as first-class
    fields; ``evidence`` never carries employee PII.
    """

    check_id: uuid.UUID
    employee_id: uuid.UUID | None
    employee_number: str | None
    name: str | None
    department_name: str | None
    check_type: str
    severity: str
    owner_rule: str
    title: str
    description: str
    evidence: dict[str, Any]
    status: str
    owner_user_id: uuid.UUID | None
    created_at: datetime


class ComplianceRiskGroupOut(BaseModel):
    """One check type's severity-weighted risk (open findings only)."""

    check_type: str
    weighted_open_score: int
    open_count: int
    total_count: int


class ComplianceOrgOut(BaseModel):
    """L1 aggregate response — never carries an employee identifier/name."""

    total_findings: int
    open_findings: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    risk_ranked: list[ComplianceRiskGroupOut]
    generated_at: datetime
    narrative: str


class ComplianceStatusWrite(BaseModel):
    """Body for a status POST (``erp.hr.ai.acknowledge``).

    The compliance lifecycle is ``open -> acknowledged -> resolved``.
    """

    status: str = Field(pattern="^(acknowledged|resolved)$")


def compliance_finding_to_out(r: ComplianceFindingRow) -> ComplianceFindingOut:
    return ComplianceFindingOut(
        check_id=r.check_id if r.check_id is not None else uuid.uuid4(),
        employee_id=r.employee_id,
        employee_number=r.employee_number,
        name=f"{r.first_name or ''} {r.last_name or ''}".strip() or None,
        department_name=r.department_name,
        check_type=r.check_type,
        severity=r.severity,
        owner_rule=r.owner_rule,
        title=r.title,
        description=r.description,
        evidence=r.evidence,
        status=r.status,
        owner_user_id=r.owner_user_id,
        created_at=r.created_at,
    )


def compliance_org_to_out(summary: ComplianceOrgSummary) -> ComplianceOrgOut:
    return ComplianceOrgOut(
        total_findings=summary.total_findings,
        open_findings=summary.open_findings,
        by_type=summary.by_type,
        by_severity=summary.by_severity,
        risk_ranked=[
            ComplianceRiskGroupOut(
                check_type=g.check_type,
                weighted_open_score=g.weighted_open_score,
                open_count=g.open_count,
                total_count=g.total_count,
            )
            for g in summary.risk_ranked
        ],
        generated_at=summary.generated_at,
        narrative=summary.narrative,
    )


__all__ = [
    "AnomalyOrgOut",
    "AttritionDetailOut",
    "AttritionSummaryOut",
    "ComplianceFindingOut",
    "ComplianceOrgOut",
    "ComplianceRiskGroupOut",
    "ComplianceStatusWrite",
    "DepartmentCount",
    "DepartmentCountOut",
    "DepartmentQualityOut",
    "DepartmentRiskOut",
    "EmployeeQualityOut",
    "EmployeeRiskOut",
    "FactorOut",
    "HeadcountPoint",
    "HeadcountPointOut",
    "HrEvalRunWrite",
    "HrEvalWriteOut",
    "LeaveAnomalyOut",
    "LeaveBlackoutOut",
    "LeaveBlackoutWrite",
    "LeaveSuggestionOut",
    "Overview",
    "OverviewOut",
    "PayrollAnomalyDispositionWrite",
    "PayrollAnomalyOrgOut",
    "PayrollAnomalyOut",
    "PublicHolidayOut",
    "PublicHolidayWrite",
    "QualityOrgOut",
    "SuggestionOrgOut",
    "TenureBand",
    "TenureBandOut",
    "TenureSummary",
    "TenureSummaryOut",
    "UtilizationAlertOut",
    "UtilizationOrgOut",
    "anomaly_org_to_out",
    "anomaly_to_out",
    "attrition_l1_to_out",
    "attrition_l2_to_out",
    "compliance_finding_to_out",
    "compliance_org_to_out",
    "employee_quality_to_out",
    "leave_blackout_to_out",
    "overview_to_out",
    "payroll_anomaly_org_to_out",
    "payroll_anomaly_to_out",
    "public_holiday_to_out",
    "quality_org_to_out",
    "suggestion_org_to_out",
    "suggestion_to_out",
    "tenure_to_out",
    "utilization_alert_to_out",
    "utilization_org_to_out",
]
