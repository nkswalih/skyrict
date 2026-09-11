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
from core.features.hr.models.leave_request import LeaveRequestModel, LeaveRequestStatus
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
    current_benefit_adjustments: Decimal
    previous_benefit_adjustments: Decimal
    benefit_delta: Decimal
    department_breakdown: list[DepartmentCostDelta] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LeavePayPair:
    """One monthly observation for the L3 leave-pay correlation (HR-AI-003, C2).

    ``overtime`` is the cover overtime paid in the run; ``leave_days`` is the
    approved leave falling inside the run's period. The correlation is a
    derived statistic computed from these pairs (never a stored figure).
    """

    period_start: date
    run_code: str
    leave_days: int
    overtime: Decimal


_OVERTIME_SUM = func.coalesce(
    func.sum(text("(erp_payroll_entries.adjustments->>'overtime_amount')::numeric")), 0
)

# Benefit adjustments: an allowlist over the existing ``adjustments`` JSONB so
# the L3 cost movement exposes a benefit figure without inventing a second
# "benefit" domain conflicting with HR benefit plans/elections. The domain's
# adjustment keys are overtime_amount/amount/bonus/other_deduction/reason and
# the seed only writes overtime_amount, so a demo benefit_delta is normally 0
# until real data populates amount/bonus.
_BENEFIT_ADJUSTMENT_KEYS = ("bonus", "amount")

_BENEFIT_SUM = func.coalesce(
    func.sum(
        func.coalesce(text("(erp_payroll_entries.adjustments->>'bonus')::numeric"), 0)
        + func.coalesce(text("(erp_payroll_entries.adjustments->>'amount')::numeric"), 0)
    ),
    0,
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

        (
            current_count,
            current_overtime,
            current_benefit,
        ) = await self._entry_stats(tenant_id, current.id)
        (
            previous_count,
            previous_overtime,
            previous_benefit,
        ) = await self._entry_stats(tenant_id, previous.id)

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
            current_benefit_adjustments=current_benefit,
            previous_benefit_adjustments=previous_benefit,
            benefit_delta=current_benefit - previous_benefit,
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

    async def leave_pay_pairs(self, tenant_id: uuid.UUID, *, limit: int = 12) -> list[LeavePayPair]:
        """Monthly (approved leave days, overtime paid) over the last runs.

        One row per paid/approved run, newest first, up to ``limit`` months.
        Leave days are the approved requests overlapping the run's period;
        overtime is the sum of ``adjustments->>'overtime_amount'`` in the run.
        Returns an empty list when the tenant has no completed runs.
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
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        if not runs:
            return []
        run_ids = [run.id for run in runs]

        ot_rows = (
            await self.session.execute(
                select(PayrollEntryModel.run_id, _OVERTIME_SUM)
                .where(
                    PayrollEntryModel.tenant_id == tenant_id,
                    PayrollEntryModel.run_id.in_(run_ids),
                )
                .group_by(PayrollEntryModel.run_id)
            )
        ).all()
        overtime_by_run = {str(r[0]): Decimal(str(r[1])) for r in ot_rows}

        pairs: list[LeavePayPair] = []
        for run in runs:
            leave_days = (
                await self.session.execute(
                    select(func.coalesce(func.sum(LeaveRequestModel.days), 0)).where(
                        LeaveRequestModel.tenant_id == tenant_id,
                        LeaveRequestModel.status == LeaveRequestStatus.APPROVED,
                        LeaveRequestModel.start_date <= run.period_end,
                        LeaveRequestModel.end_date >= run.period_start,
                    )
                )
            ).scalar_one()
            pairs.append(
                LeavePayPair(
                    period_start=run.period_start,
                    run_code=str(run.run_code),
                    leave_days=int(leave_days),
                    overtime=overtime_by_run.get(str(run.id), Decimal("0")),
                )
            )
        return pairs

    async def _entry_stats(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[int, Decimal, Decimal]:
        """(entry count, overtime sum, benefit-adjustment sum) for one run."""
        row = (
            await self.session.execute(
                select(func.count(PayrollEntryModel.id), _OVERTIME_SUM, _BENEFIT_SUM).where(
                    PayrollEntryModel.tenant_id == tenant_id,
                    PayrollEntryModel.run_id == run_id,
                )
            )
        ).one()
        return int(row[0]), Decimal(str(row[1])), Decimal(str(row[2]))

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
