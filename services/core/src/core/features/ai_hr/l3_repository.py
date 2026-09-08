"""L3 payroll-cost source data repository (HR-AI-003).

Read-only projection over the frozen payroll snapshot: the month-over-month
cost movement (headcount, gross, net, overtime) between the two most recent
paid/approved runs, plus a per-department net delta. The department join
mirrors ``PayrollRepository.department_net_summary``; overtime is summed from
``adjustments->>'overtime_amount'``. No employee row is ever projected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from core.features.hr.models.department import DepartmentModel
from core.features.hr.models.employee import EmployeeModel
from core.features.payroll.models.payroll_entry import PayrollEntryModel
from core.features.payroll.models.payroll_run import PayrollRunModel, PayrollRunStatus


@dataclass(frozen=True, slots=True)
class RunPeriod:
    """One payroll run's period identity."""

    period_start: date
    period_end: date
    run_code: str


@dataclass(frozen=True, slots=True)
class DepartmentCostDelta:
    """Net pay movement for one department across the two compared runs."""

    department_name: str
    current_net: Decimal
    previous_net: Decimal
    net_delta: Decimal


@dataclass(frozen=True, slots=True)
class PayrollCostMovement:
    """The L3 month-over-month cost movement between the 2 most recent runs."""

    current_period: RunPeriod
    previous_period: RunPeriod
    current_headcount: int
    previous_headcount: int
    headcount_delta: int
    current_gross: Decimal
    previous_gross: Decimal
    gross_delta: Decimal
    current_net: Decimal
    previous_net: Decimal
    net_delta: Decimal
    current_overtime: Decimal
    previous_overtime: Decimal
    overtime_delta: Decimal
    department_breakdown: list[DepartmentCostDelta] = field(default_factory=list)


_OVERTIME_SUM = func.coalesce(
    func.sum(text("(erp_payroll_entries.adjustments->>'overtime_amount')::numeric")), 0
)

_PAID_OR_APPROVED = (PayrollRunStatus.PAID, PayrollRunStatus.APPROVED)


class L3Repository:
    """Read projection for the L3 cost-movement source data (HR-AI-003)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def payroll_cost_movement(self, tenant_id: uuid.UUID) -> PayrollCostMovement | None:
        """Month-over-month movement for the 2 most recent paid/approved runs.

        Returns ``None`` when the tenant has fewer than two such runs.
        """
        runs = (
            (
                await self.session.execute(
                    select(PayrollRunModel)
                    .where(
                        PayrollRunModel.tenant_id == tenant_id,
                        PayrollRunModel.status.in_(_PAID_OR_APPROVED),
                    )
                    .order_by(PayrollRunModel.period_start.desc())
                    .limit(2)
                )
            )
            .scalars()
            .all()
        )
        if len(runs) < 2:
            return None
        current, previous = runs

        current_count, current_overtime = await self._entry_stats(tenant_id, current.id)
        previous_count, previous_overtime = await self._entry_stats(tenant_id, previous.id)

        current_gross = Decimal(str(current.total_gross or 0))
        current_net = Decimal(str(current.total_net or 0))
        previous_gross = Decimal(str(previous.total_gross or 0))
        previous_net = Decimal(str(previous.total_net or 0))

        current_depts = await self._dept_nets(tenant_id, current.id)
        previous_depts = await self._dept_nets(tenant_id, previous.id)

        return PayrollCostMovement(
            current_period=RunPeriod(
                current.period_start, current.period_end, str(current.run_code)
            ),
            previous_period=RunPeriod(
                previous.period_start, previous.period_end, str(previous.run_code)
            ),
            current_headcount=current_count,
            previous_headcount=previous_count,
            headcount_delta=current_count - previous_count,
            current_gross=current_gross,
            previous_gross=previous_gross,
            gross_delta=current_gross - previous_gross,
            current_net=current_net,
            previous_net=previous_net,
            net_delta=current_net - previous_net,
            current_overtime=current_overtime,
            previous_overtime=previous_overtime,
            overtime_delta=current_overtime - previous_overtime,
            department_breakdown=[
                DepartmentCostDelta(
                    department_name=name,
                    current_net=current_depts.get(name, Decimal("0")),
                    previous_net=previous_depts.get(name, Decimal("0")),
                    net_delta=current_depts.get(name, Decimal("0"))
                    - previous_depts.get(name, Decimal("0")),
                )
                for name in sorted(set(current_depts) | set(previous_depts))
            ],
        )

    async def _entry_stats(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> tuple[int, Decimal]:
        """(entry count, overtime sum) for one run."""
        row = (
            await self.session.execute(
                select(func.count(PayrollEntryModel.id), _OVERTIME_SUM).where(
                    PayrollEntryModel.tenant_id == tenant_id,
                    PayrollEntryModel.run_id == run_id,
                )
            )
        ).one()
        return int(row[0]), Decimal(str(row[1]))

    async def _dept_nets(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Decimal]:
        """Run net totals bucketed by department, ``(name, net)`` by name."""
        dept = aliased(DepartmentModel)
        stmt = (
            select(
                func.coalesce(dept.name, "Unassigned").label("department_name"),
                func.sum(PayrollEntryModel.net),
            )
            .select_from(PayrollEntryModel)
            .join(
                EmployeeModel,
                (EmployeeModel.tenant_id == PayrollEntryModel.tenant_id)
                & (EmployeeModel.id == PayrollEntryModel.employee_id),
            )
            .outerjoin(
                dept,
                (dept.tenant_id == EmployeeModel.tenant_id)
                & (dept.id == EmployeeModel.department_id),
            )
            .where(
                PayrollEntryModel.tenant_id == tenant_id,
                PayrollEntryModel.run_id == run_id,
            )
            .group_by(dept.name)
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(r.department_name): Decimal(str(r[1] or 0)) for r in rows}