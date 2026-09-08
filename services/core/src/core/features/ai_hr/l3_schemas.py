"""Pydantic response schemas for the L3 payroll-cost source data (HR-AI-003).

Money values are serialized as strings (the narrator convention) so decimals
travel losslessly to ai-agent. Mirrors :class:`PayrollCostMovement` from
:mod:`core.features.ai_hr.l3_repository`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from core.features.ai_hr.l3_repository import PayrollCostMovement


class DepartmentDeltaOut(BaseModel):
    department_name: str
    current_net: str
    previous_net: str
    net_delta: str


class PayrollCostMovementOut(BaseModel):
    current_period_start: date
    current_period_end: date
    current_run_code: str
    previous_period_start: date
    previous_period_end: date
    previous_run_code: str
    current_headcount: int
    previous_headcount: int
    headcount_delta: int
    current_gross: str
    previous_gross: str
    gross_delta: str
    current_net: str
    previous_net: str
    net_delta: str
    current_overtime: str
    previous_overtime: str
    overtime_delta: str
    department_breakdown: list[DepartmentDeltaOut]


def _money(value: Decimal) -> str:
    return str(value)


def movement_to_out(m: PayrollCostMovement) -> PayrollCostMovementOut:
    """Convert a :class:`PayrollCostMovement` to its string-typed response shape."""
    return PayrollCostMovementOut(
        current_period_start=m.current_period.period_start,
        current_period_end=m.current_period.period_end,
        current_run_code=m.current_period.run_code,
        previous_period_start=m.previous_period.period_start,
        previous_period_end=m.previous_period.period_end,
        previous_run_code=m.previous_period.run_code,
        current_headcount=m.current_headcount,
        previous_headcount=m.previous_headcount,
        headcount_delta=m.headcount_delta,
        current_gross=_money(m.current_gross),
        previous_gross=_money(m.previous_gross),
        gross_delta=_money(m.gross_delta),
        current_net=_money(m.current_net),
        previous_net=_money(m.previous_net),
        net_delta=_money(m.net_delta),
        current_overtime=_money(m.current_overtime),
        previous_overtime=_money(m.previous_overtime),
        overtime_delta=_money(m.overtime_delta),
        department_breakdown=[
            DepartmentDeltaOut(
                department_name=d.department_name,
                current_net=_money(d.current_net),
                previous_net=_money(d.previous_net),
                net_delta=_money(d.net_delta),
            )
            for d in m.department_breakdown
        ],
    )