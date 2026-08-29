"""Pydantic response schemas for the L1 HR/Payroll AI endpoints.

Mirror the aggregate dataclasses from :mod:`core.features.ai_hr.repository`.
None of these models carries an employee identifier, name, or per-person value —
they are L1 shapes by construction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from core.features.ai_hr.attrition_repository import ScoredRisk
from core.features.ai_hr.quality_repository import EmployeeQuality
from core.features.ai_hr.quality_service import QualityOrgKpi
from core.features.ai_hr.repository import (
    DepartmentCount,
    HeadcountPoint,
    Overview,
    TenureBand,
    TenureSummary,
)
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
    """L2 individual risk — the ONLY shape allowed to carry a name/number."""

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
    """L1 aggregate response — never carries an employee identifier/name."""

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
    """L1 aggregate response — never carries an employee identifier/name."""

    total_scored: int
    average_score: float
    grade_distribution: dict[str, int]
    department_averages: list[DepartmentQualityOut]
    generated_at: datetime
    narrative: str


class EmployeeQualityOut(BaseModel):
    """L2 individual quality — the ONLY shape allowed to carry name/number."""

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
    """L1 aggregate response — never carries an employee identifier/name."""

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


__all__ = [
    "AttritionDetailOut",
    "AttritionSummaryOut",
    "DepartmentCount",
    "DepartmentCountOut",
    "DepartmentQualityOut",
    "DepartmentRiskOut",
    "EmployeeQualityOut",
    "EmployeeRiskOut",
    "FactorOut",
    "HeadcountPoint",
    "HeadcountPointOut",
    "Overview",
    "OverviewOut",
    "QualityOrgOut",
    "TenureBand",
    "TenureBandOut",
    "TenureSummary",
    "TenureSummaryOut",
    "UtilizationAlertOut",
    "UtilizationOrgOut",
    "attrition_l1_to_out",
    "attrition_l2_to_out",
    "employee_quality_to_out",
    "overview_to_out",
    "quality_org_to_out",
    "tenure_to_out",
    "utilization_alert_to_out",
    "utilization_org_to_out",
]
