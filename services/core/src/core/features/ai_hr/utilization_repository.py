"""Utilization-alert repository for the HR/Payroll AI slice (HR-AI-002, 8.1.4).

Projects per-employee leave-balance signals from the ERP tables and persists
``ai_hr_utilization_alerts`` rows for the scan run. Signal mapping:

  - forfeit_risk: an accrual leave type has an unused balance while the year-end
    is inside the forfeit window (default 60 days). ``balance_days`` is the
    current balance; ``projected_forfeiture_days`` is what would be lost at
    year end (the full balance).
  - negative_accrual: this year's unrestricted movement sum for an accrual type
    is negative (consumption exceeded accrual). ``balance_days`` floors at 0
    because the materialized ``erp_leave_balances`` row can never be negative
    (CK ``balance >= 0``); the true shortfall lives in the evidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.ai_hr.models.utilization_alert import UtilizationAlertModel
from core.features.hr.models.department import DepartmentModel
from core.features.hr.models.employee import EmployeeModel, EmploymentStatus
from core.features.hr.models.leave_balance import LeaveBalanceModel
from core.features.hr.models.leave_movement import LeaveMovementModel
from core.features.hr.models.leave_type import LeaveTypeModel

_ACTIVE = (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE)


@dataclass(frozen=True, slots=True)
class UtilizationAlert:
    """One computed utilization finding for a single employee."""

    employee_id: uuid.UUID
    alert_type: str
    severity: str
    balance_days: int
    projected_forfeiture_days: int | None
    days_remaining_in_year: int | None
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Read-side enrichment (populated on list, not on scan).
    employee_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    department_name: str | None = None
    department_id: uuid.UUID | None = None
    status: str | None = None
    leave_type: str | None = None


class AiHrUtilizationRepository:
    """Read/write access to utilization signals and persisted alerts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- signal projection ----------------------------------------------------

    async def build_utilization_rows(self, tenant_id: uuid.UUID) -> list[UtilizationAlert]:
        """Per-active-employee utilization signals (alert_type/severity added later)."""
        today = date.today()
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)
        last_day = (year_end - today).days

        balances = (
            select(
                LeaveBalanceModel.employee_id.label("employee_id"),
                LeaveBalanceModel.leave_type.label("leave_type"),
                LeaveBalanceModel.balance.label("balance"),
                LeaveTypeModel.code.label("leave_type_code"),
            )
            .join(
                LeaveTypeModel,
                and_(
                    LeaveTypeModel.tenant_id == LeaveBalanceModel.tenant_id,
                    LeaveTypeModel.code == LeaveBalanceModel.leave_type,
                ),
            )
            .where(
                LeaveBalanceModel.tenant_id == tenant_id,
                LeaveTypeModel.is_accrual.is_(True),
            )
        )
        balance_rows = (await self.session.execute(balances)).all()

        year_movements = (
            select(
                LeaveMovementModel.employee_id.label("employee_id"),
                LeaveMovementModel.leave_type.label("leave_type"),
                func.sum(LeaveMovementModel.qty).label("net_qty"),
            )
            .where(
                LeaveMovementModel.tenant_id == tenant_id,
                LeaveMovementModel.occurred_at >= year_start,
                LeaveMovementModel.occurred_at <= year_end,
            )
            .group_by(
                LeaveMovementModel.employee_id,
                LeaveMovementModel.leave_type,
            )
        )
        movement_rows = (await self.session.execute(year_movements)).all()
        year_net: dict[tuple[uuid.UUID, str], int] = {}
        for m in movement_rows:
            year_net[(m.employee_id, m.leave_type)] = int(m.net_qty or 0)

        active_ids = await self._active_employee_ids(tenant_id)

        alerts: list[UtilizationAlert] = []
        for b in balance_rows:
            if b.employee_id not in active_ids:
                continue
            key = (b.employee_id, b.leave_type)
            net = year_net.get(key, 0)
            if net < 0:
                alerts.append(
                    UtilizationAlert(
                        employee_id=b.employee_id,
                        alert_type="negative_accrual",
                        severity="high",
                        balance_days=0,
                        projected_forfeiture_days=None,
                        days_remaining_in_year=last_day,
                        evidence={
                            "leave_type": b.leave_type,
                            "year": today.year,
                            "year_net_qty": net,
                            "materialized_balance_floor": int(b.balance),
                        },
                    )
                )
        for b in balance_rows:
            if b.employee_id not in active_ids or int(b.balance) <= 0:
                continue
            if last_day <= self._forfeit_window():
                alerts.append(
                    UtilizationAlert(
                        employee_id=b.employee_id,
                        alert_type="forfeit_risk",
                        severity=self._forfeit_severity(int(b.balance)),
                        balance_days=int(b.balance),
                        projected_forfeiture_days=int(b.balance),
                        days_remaining_in_year=last_day,
                        evidence={
                            "leave_type": b.leave_type,
                            "year": today.year,
                            "forfeit_window_days": self._forfeit_window(),
                        },
                    )
                )
        return alerts

    async def _active_employee_ids(self, tenant_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.tenant_id == tenant_id,
            EmployeeModel.employment_status.in_(_ACTIVE),
        )
        rows = (await self.session.execute(stmt)).all()
        return {r[0] for r in rows}

    # -- persistence ----------------------------------------------------------

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        stmt = select(func.max(UtilizationAlertModel.created_at)).where(
            UtilizationAlertModel.tenant_id == tenant_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def replace_tenant_alerts(
        self, tenant_id: uuid.UUID, alerts: list[UtilizationAlert]
    ) -> None:
        """Regenerate the tenant's alert inbox for one scan run."""
        await self.session.execute(
            delete(UtilizationAlertModel).where(UtilizationAlertModel.tenant_id == tenant_id)
        )
        if not alerts:
            return
        now = datetime.now(UTC)
        values = [
            {
                "tenant_id": tenant_id,
                "employee_id": a.employee_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "balance_days": a.balance_days,
                "projected_forfeiture_days": a.projected_forfeiture_days,
                "days_remaining_in_year": a.days_remaining_in_year,
                "evidence": a.evidence,
                "created_at": now,
            }
            for a in alerts
        ]
        await self.session.execute(insert(UtilizationAlertModel), values)

    # -- reads ----------------------------------------------------------------

    async def list_alerts(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[UtilizationAlert]:
        stmt = (
            select(
                UtilizationAlertModel.employee_id,
                UtilizationAlertModel.alert_type,
                UtilizationAlertModel.severity,
                UtilizationAlertModel.balance_days,
                UtilizationAlertModel.projected_forfeiture_days,
                UtilizationAlertModel.days_remaining_in_year,
                UtilizationAlertModel.evidence,
                UtilizationAlertModel.created_at,
                UtilizationAlertModel.status,
                EmployeeModel.employee_number,
                EmployeeModel.first_name,
                EmployeeModel.last_name,
                EmployeeModel.department_id,
                DepartmentModel.name.label("department_name"),
            )
            .join(
                EmployeeModel,
                and_(
                    EmployeeModel.tenant_id == UtilizationAlertModel.tenant_id,
                    EmployeeModel.id == UtilizationAlertModel.employee_id,
                ),
            )
            .outerjoin(
                DepartmentModel,
                and_(
                    DepartmentModel.tenant_id == EmployeeModel.tenant_id,
                    DepartmentModel.id == EmployeeModel.department_id,
                ),
            )
            .where(UtilizationAlertModel.tenant_id == tenant_id)
            .order_by(UtilizationAlertModel.created_at.desc())
        )
        if employee_id is not None:
            stmt = stmt.where(UtilizationAlertModel.employee_id == employee_id)
        rows = (await self.session.execute(stmt)).all()
        return [
            UtilizationAlert(
                employee_id=r.employee_id,
                alert_type=r.alert_type,
                severity=r.severity,
                balance_days=r.balance_days,
                projected_forfeiture_days=r.projected_forfeiture_days,
                days_remaining_in_year=r.days_remaining_in_year,
                evidence=r.evidence,
                created_at=r.created_at,
                status=r.status,
                employee_number=r.employee_number,
                first_name=r.first_name,
                last_name=r.last_name,
                department_name=r.department_name,
                department_id=r.department_id,
                leave_type=cast("dict[str, Any]", r.evidence).get("leave_type"),
            )
            for r in rows
        ]

    # -- constants (tunable, documented in the spec) --------------------------

    def _forfeit_window(self) -> int:
        return self.FORFEIT_WINDOW_DAYS

    FORFEIT_WINDOW_DAYS = 60

    @staticmethod
    def _forfeit_severity(balance: int) -> str:
        if balance >= 20:
            return "high"
        if balance >= 10:
            return "medium"
        return "low"


__all__ = ["AiHrUtilizationRepository", "UtilizationAlert"]
