"""Leave pattern anomaly repository (HR-AI-002, 8.2.1 — the anomaly inbox).

Scans approved/pending leave requests in a trailing window and finds per-team
pattern deviations:

  - ``leave_overuse``: an employee consumes >= 3x the team's median leave-days
    (only when the median itself is >= 1 day).
  - ``frequent_absence``: an employee files >= 3x the team's median request
    count (only when the median itself is >= 1 request).

Severity scales with the ratio (>=5x critical, >=4x high, >=3x medium). The
*team-size gate* abstains entirely for teams with fewer than 4 active members —
the Gherkin case drives no persisted rows for a thin baseline. Findings are
persisted into ``ai_hr_leave_anomalies`` by replace-tenant scan.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.ai_hr.models.leave_anomaly import LeaveAnomalyModel
from core.features.hr.models.department import DepartmentModel
from core.features.hr.models.employee import EmployeeModel, EmploymentStatus
from core.features.hr.models.leave_request import LeaveRequestModel, LeaveRequestStatus

_ACTIVE = (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE)
_INCLUDED_STATES = (LeaveRequestStatus.APPROVED, LeaveRequestStatus.PENDING)


@dataclass(frozen=True, slots=True)
class LeaveAnomaly:
    """One computed leave-pattern finding for a single employee."""

    employee_id: uuid.UUID
    anomaly_type: str
    severity: str
    title: str
    description: str
    team_id: uuid.UUID | None
    team_size: int
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Read-side enrichment (populated on list, not on scan).
    employee_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    department_name: str | None = None
    status: str | None = None


class AiHrAnomalyRepository:
    """Read/write access to leave-pattern signals and persisted findings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- signal projection ----------------------------------------------------

    async def build_anomaly_rows(self, tenant_id: uuid.UUID) -> list[LeaveAnomaly]:
        """Compute per-team pattern deviations for the current scan."""
        today = date.today()
        window_start = today - timedelta(days=self.TRAILING_DAYS)

        employees = select(
            EmployeeModel.id.label("employee_id"),
            EmployeeModel.department_id,
        ).where(
            EmployeeModel.tenant_id == tenant_id,
            EmployeeModel.employment_status.in_(_ACTIVE),
        )
        employee_rows = (await self.session.execute(employees)).all()
        by_department: dict[uuid.UUID | None, list[uuid.UUID]] = {}
        for r in employee_rows:
            by_department.setdefault(r.department_id, []).append(r.employee_id)

        req_stmt = select(
            LeaveRequestModel.employee_id,
            LeaveRequestModel.start_date,
            LeaveRequestModel.days,
            LeaveRequestModel.leave_type,
        ).where(
            LeaveRequestModel.tenant_id == tenant_id,
            LeaveRequestModel.status.in_(_INCLUDED_STATES),
            LeaveRequestModel.start_date >= window_start,
            LeaveRequestModel.start_date <= today,
        )
        req_rows = (await self.session.execute(req_stmt)).all()
        requests: dict[uuid.UUID, list[Any]] = {}
        for rq in req_rows:
            requests.setdefault(rq.employee_id, []).append(rq)

        return self._compute(by_department, requests)

    @classmethod
    def _compute(
        cls,
        by_department: dict[uuid.UUID | None, list[uuid.UUID]],
        requests: dict[uuid.UUID, list[Any]],
    ) -> list[LeaveAnomaly]:
        """Pure rule engine over grouped members + requests — unit-testable."""
        anomalies: list[LeaveAnomaly] = []
        for department_id, members in by_department.items():
            if len(members) < cls.MIN_TEAM_SIZE:
                continue  # team-size gate: abstain for thin baselines
            days_by: dict[uuid.UUID, int] = {}
            count_by: dict[uuid.UUID, int] = {}
            for mid in members:
                member_reqs = requests.get(mid, [])
                days_by[mid] = sum(int(r.days or 0) for r in member_reqs)
                count_by[mid] = len(member_reqs)
            med_days = median(days_by.values())
            med_count = median(count_by.values())
            for mid in members:
                if mid not in requests:
                    continue
                member_reqs = requests[mid]
                total_days = days_by[mid]
                count = count_by[mid]
                first_start = str(min(rq.start_date for rq in member_reqs))
                if med_days >= 1 and total_days >= 3 * med_days:
                    ratio = total_days / med_days
                    severity = cls._ratio_severity(ratio)
                    anomalies.append(
                        LeaveAnomaly(
                            employee_id=mid,
                            anomaly_type="leave_overuse",
                            severity=severity,
                            title="Above-average leave consumption",
                            description=(
                                f"{total_days} leave day(s) used in the trailing "
                                f"{cls.TRAILING_DAYS} days vs a team median of "
                                f"{med_days:.1f}."
                            ),
                            team_id=department_id,
                            team_size=len(members),
                            evidence={
                                "window_days": cls.TRAILING_DAYS,
                                "leave_days": total_days,
                                "team_median_days": round(med_days, 2),
                                "request_count": count,
                                "first_start": first_start,
                            },
                        )
                    )
                if med_count >= 1 and count >= 3 * med_count:
                    ratio = count / med_count
                    severity = cls._ratio_severity(ratio)
                    anomalies.append(
                        LeaveAnomaly(
                            employee_id=mid,
                            anomaly_type="frequent_absence",
                            severity=severity,
                            title="Frequent leave requests",
                            description=(
                                f"{count} leave request(s) in the trailing "
                                f"{cls.TRAILING_DAYS} days vs a team median of "
                                f"{med_count:.1f}."
                            ),
                            team_id=department_id,
                            team_size=len(members),
                            evidence={
                                "window_days": cls.TRAILING_DAYS,
                                "request_count": count,
                                "team_median_count": round(med_count, 2),
                                "leave_days": total_days,
                            },
                        )
                    )
        return anomalies

    # -- persistence ----------------------------------------------------------

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        stmt = select(func.max(LeaveAnomalyModel.created_at)).where(
            LeaveAnomalyModel.tenant_id == tenant_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def replace_tenant_anomalies(
        self, tenant_id: uuid.UUID, rows: list[LeaveAnomaly]
    ) -> None:
        """Regenerate the tenant's anomaly inbox for one scan run."""
        await self.session.execute(
            delete(LeaveAnomalyModel).where(LeaveAnomalyModel.tenant_id == tenant_id)
        )
        if not rows:
            return
        now = datetime.now(UTC)
        values = [
            {
                "tenant_id": tenant_id,
                "employee_id": a.employee_id,
                "anomaly_type": a.anomaly_type,
                "severity": a.severity,
                "title": a.title,
                "description": a.description,
                "team_id": a.team_id,
                "team_size": a.team_size,
                "evidence": a.evidence,
                "created_at": now,
            }
            for a in rows
        ]
        await self.session.execute(insert(LeaveAnomalyModel), values)

    # -- reads ----------------------------------------------------------------

    async def list_anomalies(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[LeaveAnomaly]:
        stmt = (
            select(
                LeaveAnomalyModel.employee_id,
                LeaveAnomalyModel.anomaly_type,
                LeaveAnomalyModel.severity,
                LeaveAnomalyModel.title,
                LeaveAnomalyModel.description,
                LeaveAnomalyModel.team_id,
                LeaveAnomalyModel.team_size,
                LeaveAnomalyModel.evidence,
                LeaveAnomalyModel.status,
                LeaveAnomalyModel.created_at,
                EmployeeModel.employee_number,
                EmployeeModel.first_name,
                EmployeeModel.last_name,
                DepartmentModel.name.label("department_name"),
            )
            .join(
                EmployeeModel,
                and_(
                    EmployeeModel.tenant_id == LeaveAnomalyModel.tenant_id,
                    EmployeeModel.id == LeaveAnomalyModel.employee_id,
                ),
            )
            .outerjoin(
                DepartmentModel,
                and_(
                    DepartmentModel.tenant_id == EmployeeModel.tenant_id,
                    DepartmentModel.id == EmployeeModel.department_id,
                ),
            )
            .where(LeaveAnomalyModel.tenant_id == tenant_id)
            .order_by(LeaveAnomalyModel.created_at.desc())
        )
        if employee_id is not None:
            stmt = stmt.where(LeaveAnomalyModel.employee_id == employee_id)
        rows = (await self.session.execute(stmt)).all()
        return [
            LeaveAnomaly(
                employee_id=r.employee_id,
                anomaly_type=r.anomaly_type,
                severity=r.severity,
                title=r.title,
                description=r.description,
                team_id=r.team_id,
                team_size=r.team_size,
                evidence=r.evidence,
                status=r.status,
                created_at=r.created_at,
                employee_number=r.employee_number,
                first_name=r.first_name,
                last_name=r.last_name,
                department_name=r.department_name,
            )
            for r in rows
        ]

    # -- constants (tunable, documented in the spec) --------------------------

    TRAILING_DAYS = 90
    MIN_TEAM_SIZE = 4

    @staticmethod
    def _ratio_severity(ratio: float) -> str:
        if ratio >= 5:
            return "critical"
        if ratio >= 4:
            return "high"
        return "medium"


__all__ = ["AiHrAnomalyRepository", "LeaveAnomaly"]
