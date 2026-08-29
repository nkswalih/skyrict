"""Leave pattern anomaly repository (HR-AI-002, 8.2.1 — the anomaly inbox).

Scans approved/pending leave requests in a trailing window and finds per-team
pattern deviations. The detection itself lives in the PURE shared engine
:mod:`skyrict_common.ai_hr_rules` — the ai-agent eval harness grades the exact
same code — and this repository is the I/O boundary (projection + persistence):

  - ``leave_overuse``: consumes >= 3x the team's median leave-days.
  - ``frequent_absence``: files >= 3x the team's median request count.
  - ``short_notice_monday_friday``: a Monday/Friday-touching block filed with
    < 14 days' notice and >= 3x the median.
  - ``pre_holiday_spike``: leave within 2 days of a public holiday and >= 3x
    the median.

The *team-size gate* abstains entirely for teams with fewer than 4 active
members — thin baselines drive no persisted rows. Findings are persisted into
``ai_hr_leave_anomalies`` by replace-tenant scan.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.ai_hr.models.leave_anomaly import LeaveAnomalyModel
from core.features.ai_hr.models.public_holiday import AiHrPublicHolidayModel
from core.features.hr.models.department import DepartmentModel
from core.features.hr.models.employee import EmployeeModel, EmploymentStatus
from core.features.hr.models.leave_request import LeaveRequestModel, LeaveRequestStatus
from skyrict_common.ai_hr_rules import (
    Holiday,
    RequestSignal,
    detect_leave_pattern_anomalies,
    ratio_severity,
)

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

        employees = select(
            EmployeeModel.id.label("employee_id"),
            EmployeeModel.department_id,
        ).where(
            EmployeeModel.tenant_id == tenant_id,
            EmployeeModel.employment_status.in_(_ACTIVE),
        )
        employee_rows = (await self.session.execute(employees)).all()
        members: dict[uuid.UUID | None, list[uuid.UUID]] = {}
        for r in employee_rows:
            members.setdefault(r.department_id, []).append(r.employee_id)

        req_stmt = select(
            LeaveRequestModel.id,
            LeaveRequestModel.employee_id,
            LeaveRequestModel.start_date,
            LeaveRequestModel.end_date,
            LeaveRequestModel.days,
            LeaveRequestModel.leave_type,
            LeaveRequestModel.created_at,
        ).where(
            LeaveRequestModel.tenant_id == tenant_id,
            LeaveRequestModel.status.in_(_INCLUDED_STATES),
        )
        req_rows = (await self.session.execute(req_stmt)).all()
        requests: dict[uuid.UUID, list[RequestSignal]] = {}
        for rq in req_rows:
            requests.setdefault(rq.employee_id, []).append(
                RequestSignal(
                    request_id=rq.id,
                    employee_id=rq.employee_id,
                    start_date=rq.start_date,
                    end_date=rq.end_date,
                    days=int(rq.days or 0),
                    leave_type=rq.leave_type,
                    filed_on=rq.created_at.date(),
                )
            )

        holidays_stmt = select(
            AiHrPublicHolidayModel.calendar_date,
            AiHrPublicHolidayModel.name,
            AiHrPublicHolidayModel.department_id,
        ).where(AiHrPublicHolidayModel.tenant_id == tenant_id)
        holidays = [
            Holiday(
                calendar_date=h.calendar_date,
                name=h.name,
                department_id=h.department_id,
            )
            for h in (await self.session.execute(holidays_stmt)).all()
        ]

        return self._compute(members, requests, holidays, today)

    @classmethod
    def _compute(
        cls,
        members: dict[uuid.UUID | None, list[uuid.UUID]],
        requests: dict[uuid.UUID, list[RequestSignal]],
        holidays: list[Holiday] | None = None,
        today: date | None = None,
    ) -> list[LeaveAnomaly]:
        """Run the PURE shared engine and map findings onto the row shape."""
        now = datetime.now(UTC)
        return [
            LeaveAnomaly(
                employee_id=found.employee_id,
                anomaly_type=found.anomaly_type,
                severity=found.severity,
                title=found.title,
                description=found.description,
                team_id=found.team_id,
                team_size=found.team_size,
                evidence=found.evidence,
                created_at=now,
            )
            for found in detect_leave_pattern_anomalies(
                members=members,
                requests_by_employee=requests,
                holidays=holidays or (),
                today=today or date.today(),
                trailing_days=cls.TRAILING_DAYS,
                min_team_size=cls.MIN_TEAM_SIZE,
                short_notice_days=cls.SHORT_NOTICE_DAYS,
                short_notice_pressing_days=cls.SHORT_NOTICE_PRESSING_DAYS,
                pre_holiday_adjacency_days=cls.PRE_HOLIDAY_ADJACENCY_DAYS,
                spike_ratio=cls.SPIKE_RATIO,
            )
        ]

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
    SHORT_NOTICE_DAYS = 14
    SHORT_NOTICE_PRESSING_DAYS = 3
    PRE_HOLIDAY_ADJACENCY_DAYS = 2
    SPIKE_RATIO = 3.0

    @staticmethod
    def _ratio_severity(ratio: float) -> str:
        return ratio_severity(ratio)


__all__ = ["AiHrAnomalyRepository", "LeaveAnomaly"]
