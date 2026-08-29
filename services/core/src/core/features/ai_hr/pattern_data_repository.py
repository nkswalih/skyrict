"""Tenant-config pattern data for the AI engines (holidays + blackouts).

Read/write access to ``ai_hr_public_holidays`` and
``ai_hr_leave_blackout_periods`` (migration 0024). These are lookup/config
rows — the write endpoints are gated by ``erp.hr.write`` and the engines read
them server-side under tenant context. ``department_id`` NULL means org-wide;
engines treat a row as active for an employee when it is org-wide or matches
the employee's department.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.ai_hr.models.leave_blackout_period import AiHrLeaveBlackoutPeriodModel
from core.features.ai_hr.models.public_holiday import AiHrPublicHolidayModel


@dataclass(frozen=True, slots=True)
class PublicHoliday:
    """One tenant-defined public-holiday / office-closure day."""

    holiday_id: uuid.UUID
    calendar_date: date
    name: str
    department_id: uuid.UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class LeaveBlackoutPeriod:
    """One tenant-defined leave-blackout window."""

    blackout_id: uuid.UUID
    start_date: date
    end_date: date
    department_id: uuid.UUID | None
    reason: str
    created_at: datetime


class AiHrPatternDataRepository:
    """Read/write access to the AI pattern-engine config tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- public holidays --------------------------------------------------------

    async def create_holiday(
        self,
        tenant_id: uuid.UUID,
        calendar_date: date,
        name: str,
        *,
        department_id: uuid.UUID | None = None,
    ) -> PublicHoliday:
        if not name.strip():
            raise ValueError("holiday name cannot be empty")
        model = AiHrPublicHolidayModel(
            tenant_id=tenant_id,
            calendar_date=calendar_date,
            name=name.strip(),
            department_id=department_id,
        )
        self.session.add(model)
        await self.session.flush()
        return PublicHoliday(
            holiday_id=model.id,
            calendar_date=model.calendar_date,
            name=model.name,
            department_id=model.department_id,
            created_at=model.created_at,
        )

    async def delete_holiday(self, tenant_id: uuid.UUID, holiday_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(AiHrPublicHolidayModel).where(
                AiHrPublicHolidayModel.tenant_id == tenant_id,
                AiHrPublicHolidayModel.id == holiday_id,
            )
        )
        return bool((cast("CursorResult[Any]", result)).rowcount)

    async def list_holidays(self, tenant_id: uuid.UUID) -> list[PublicHoliday]:
        rows = (
            (
                await self.session.execute(
                    select(AiHrPublicHolidayModel)
                    .where(AiHrPublicHolidayModel.tenant_id == tenant_id)
                    .order_by(AiHrPublicHolidayModel.calendar_date)
                )
            )
            .scalars()
            .all()
        )
        return [
            PublicHoliday(
                holiday_id=m.id,
                calendar_date=m.calendar_date,
                name=m.name,
                department_id=m.department_id,
                created_at=m.created_at,
            )
            for m in rows
        ]

    # -- leave blackout periods -------------------------------------------------

    async def create_blackout(
        self,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date,
        reason: str,
        *,
        department_id: uuid.UUID | None = None,
    ) -> LeaveBlackoutPeriod:
        if end_date < start_date:
            raise ValueError("blackout end_date cannot precede start_date")
        if not reason.strip():
            raise ValueError("blackout reason cannot be empty")
        model = AiHrLeaveBlackoutPeriodModel(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            department_id=department_id,
            reason=reason.strip(),
        )
        self.session.add(model)
        await self.session.flush()
        return LeaveBlackoutPeriod(
            blackout_id=model.id,
            start_date=model.start_date,
            end_date=model.end_date,
            department_id=model.department_id,
            reason=model.reason,
            created_at=model.created_at,
        )

    async def delete_blackout(self, tenant_id: uuid.UUID, blackout_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(AiHrLeaveBlackoutPeriodModel).where(
                AiHrLeaveBlackoutPeriodModel.tenant_id == tenant_id,
                AiHrLeaveBlackoutPeriodModel.id == blackout_id,
            )
        )
        return bool((cast("CursorResult[Any]", result)).rowcount)

    async def list_blackouts(self, tenant_id: uuid.UUID) -> list[LeaveBlackoutPeriod]:
        rows = (
            (
                await self.session.execute(
                    select(AiHrLeaveBlackoutPeriodModel)
                    .where(AiHrLeaveBlackoutPeriodModel.tenant_id == tenant_id)
                    .order_by(AiHrLeaveBlackoutPeriodModel.start_date)
                )
            )
            .scalars()
            .all()
        )
        return [
            LeaveBlackoutPeriod(
                blackout_id=m.id,
                start_date=m.start_date,
                end_date=m.end_date,
                department_id=m.department_id,
                reason=m.reason,
                created_at=m.created_at,
            )
            for m in rows
        ]


__all__ = [
    "AiHrPatternDataRepository",
    "LeaveBlackoutPeriod",
    "PublicHoliday",
]
