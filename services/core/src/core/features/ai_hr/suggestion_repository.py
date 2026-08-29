"""Smart leave-window suggestion repository (HR-AI-002, 8.2.4).

Consumes the forfeit-risk utilization alerts (8.1.4) and turns each into a
suggestion to spend accrued leave before the year-end window closes. The
suggested block is capped at ``SUGGESTED_BLOCK_DAYS`` (14) and is the *calmest*
usable window: candidate blocks are filtered against the employee's own
requests and any leave-blackout period (org-wide or for their department),
then ranked by how many teammates are already on leave, then by alignment with
a public holiday, then by recency (spending closer to year end). If every
usable window is blacked out or already begun, the forfeit-window fallback
(:meth:`_plan_block`) is returned as the last resort and the conflict is
spelled out in the reasons.

Suggestions NEVER auto-submit — the portal prefill is recorded as ``used`` by a
separate action. Per scan only ``pending`` suggestions are replaced;
``used``/``dismissed`` rows are kept as lifecycle history.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.ai_hr.models.leave_blackout_period import AiHrLeaveBlackoutPeriodModel
from core.features.ai_hr.models.leave_suggestion import LeaveSuggestionModel
from core.features.ai_hr.models.public_holiday import AiHrPublicHolidayModel
from core.features.ai_hr.models.utilization_alert import UtilizationAlertModel
from core.features.hr.models.department import DepartmentModel
from core.features.hr.models.employee import EmployeeModel, EmploymentStatus
from core.features.hr.models.leave_request import LeaveRequestModel, LeaveRequestStatus
from skyrict_common.ai_hr_rules import Holiday

_ACTIVE = (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE)
_INCLUDED_STATES = (LeaveRequestStatus.APPROVED, LeaveRequestStatus.PENDING)
_FORFEIT = "forfeit_risk"
_PENDING = "pending"


@dataclass(frozen=True, slots=True)
class LeaveSuggestion:
    """One suggested leave window for a single employee."""

    employee_id: uuid.UUID
    leave_type: str
    start_date: date
    end_date: date
    days: int
    reasons: list[str] = field(default_factory=list)
    status: str = _PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Read-side enrichment (populated on list, not on scan).
    employee_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    department_name: str | None = None
    suggestion_id: uuid.UUID | None = None
    used_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class _PlannedBlock:
    """A planned leave window plus the reasons for choosing it."""

    start_date: date
    end_date: date
    days: int
    reasons: tuple[str, ...]


class AiHrSuggestionRepository:
    """Read/write access to leave-window suggestions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- suggestion projection -------------------------------------------------

    async def build_suggestion_rows(self, tenant_id: uuid.UUID) -> list[LeaveSuggestion]:
        """Derive calendar-aware suggestions from open forfeit-risk alerts."""
        today = date.today()
        year_end = date(today.year, 12, 31)

        stmt = (
            select(
                UtilizationAlertModel.employee_id,
                UtilizationAlertModel.balance_days,
                UtilizationAlertModel.days_remaining_in_year,
                UtilizationAlertModel.evidence,
                EmployeeModel.department_id,
            )
            .join(
                EmployeeModel,
                and_(
                    EmployeeModel.tenant_id == UtilizationAlertModel.tenant_id,
                    EmployeeModel.id == UtilizationAlertModel.employee_id,
                ),
            )
            .where(
                UtilizationAlertModel.tenant_id == tenant_id,
                UtilizationAlertModel.alert_type == _FORFEIT,
                UtilizationAlertModel.status == "open",
                EmployeeModel.employment_status.in_(_ACTIVE),
            )
        )
        rows = (await self.session.execute(stmt)).all()

        dept_requests, own_requests = await self._load_requests(tenant_id, today, year_end)
        org_blackouts, dept_blackouts = await self._load_blackouts(tenant_id)
        org_holidays, dept_holidays = await self._load_holidays(tenant_id)

        suggestions: list[LeaveSuggestion] = []
        for r in rows:
            balance_days = int(r.balance_days or 0)
            available = int(r.days_remaining_in_year or (year_end - today).days)
            dept_id = r.department_id

            teammate_spans = [
                (rq.start_date, rq.end_date)
                for rq in dept_requests.get(dept_id, ())
                if rq.employee_id != r.employee_id
            ]
            blackout_spans = org_blackouts + dept_blackouts.get(dept_id, [])
            holidays = org_holidays + dept_holidays.get(dept_id, [])

            planned = self._plan_best_block(
                balance_days,
                available,
                today,
                year_end,
                teammate_spans=teammate_spans,
                own_spans=own_requests.get(r.employee_id, ()),
                blackout_spans=blackout_spans,
                holidays=holidays,
            )
            if planned is None:
                continue
            evidence = cast("dict[str, Any]", r.evidence)
            suggestions.append(
                LeaveSuggestion(
                    employee_id=r.employee_id,
                    leave_type=evidence.get("leave_type") or "annual",
                    start_date=planned.start_date,
                    end_date=planned.end_date,
                    days=planned.days,
                    reasons=list(planned.reasons),
                )
            )
        return suggestions

    async def _load_requests(
        self, tenant_id: uuid.UUID, today: date, year_end: date
    ) -> tuple[
        dict[uuid.UUID | None, list[Any]],
        dict[uuid.UUID, list[tuple[date, date]]],
    ]:
        """Approved/pending leave in the planning horizon, keyed as needed."""
        stmt = (
            select(
                LeaveRequestModel.employee_id,
                LeaveRequestModel.start_date,
                LeaveRequestModel.end_date,
                EmployeeModel.department_id,
            )
            .join(
                EmployeeModel,
                and_(
                    EmployeeModel.tenant_id == LeaveRequestModel.tenant_id,
                    EmployeeModel.id == LeaveRequestModel.employee_id,
                ),
            )
            .where(
                LeaveRequestModel.tenant_id == tenant_id,
                LeaveRequestModel.status.in_(_INCLUDED_STATES),
                LeaveRequestModel.start_date <= year_end,
                LeaveRequestModel.end_date >= today,
            )
        )
        rows = (await self.session.execute(stmt)).all()
        by_department: dict[uuid.UUID | None, list[Any]] = {}
        own: dict[uuid.UUID, list[tuple[date, date]]] = {}
        for rq in rows:
            by_department.setdefault(rq.department_id, []).append(rq)
            own.setdefault(rq.employee_id, []).append((rq.start_date, rq.end_date))
        return by_department, own

    async def _load_blackouts(
        self, tenant_id: uuid.UUID
    ) -> tuple[list[tuple[date, date]], dict[uuid.UUID | None, list[tuple[date, date]]]]:
        """Org-wide blackouts plus department-scoped blackouts."""
        stmt = select(
            AiHrLeaveBlackoutPeriodModel.start_date,
            AiHrLeaveBlackoutPeriodModel.end_date,
            AiHrLeaveBlackoutPeriodModel.department_id,
        ).where(AiHrLeaveBlackoutPeriodModel.tenant_id == tenant_id)
        org: list[tuple[date, date]] = []
        scoped: dict[uuid.UUID | None, list[tuple[date, date]]] = {}
        for b in (await self.session.execute(stmt)).all():
            if b.department_id is None:
                org.append((b.start_date, b.end_date))
            else:
                scoped.setdefault(b.department_id, []).append((b.start_date, b.end_date))
        return org, scoped

    async def _load_holidays(
        self, tenant_id: uuid.UUID
    ) -> tuple[list[Holiday], dict[uuid.UUID | None, list[Holiday]]]:
        """Org-wide holidays plus department-scoped holidays."""
        stmt = select(
            AiHrPublicHolidayModel.calendar_date,
            AiHrPublicHolidayModel.name,
            AiHrPublicHolidayModel.department_id,
        ).where(AiHrPublicHolidayModel.tenant_id == tenant_id)
        org: list[Holiday] = []
        scoped: dict[uuid.UUID | None, list[Holiday]] = {}
        for h in (await self.session.execute(stmt)).all():
            holiday = Holiday(
                calendar_date=h.calendar_date,
                name=h.name,
                department_id=h.department_id,
            )
            if h.department_id is None:
                org.append(holiday)
            else:
                scoped.setdefault(h.department_id, []).append(holiday)
        return org, scoped

    @staticmethod
    def _overlaps(span_start: date, span_end: date, other_start: date, other_end: date) -> bool:
        """Inclusive date-range overlap."""
        return span_start <= other_end and other_start <= span_end

    @classmethod
    def _overlaps_any(
        cls,
        span_start: date,
        span_end: date,
        spans: Sequence[tuple[date, date]],
    ) -> bool:
        return any(
            cls._overlaps(span_start, span_end, other_start, other_end)
            for other_start, other_end in spans
        )

    @staticmethod
    def _holiday_adjacent(
        span_start: date, span_end: date, holidays: Sequence[Holiday]
    ) -> Holiday | None:
        """Nearest holiday within ``PRE_HOLIDAY_ADJACENCY_DAYS`` of the span."""
        nearest: tuple[int, Holiday] | None = None
        for holiday in holidays:
            if holiday.calendar_date < span_start:
                distance = (span_start - holiday.calendar_date).days
            elif holiday.calendar_date > span_end:
                distance = (holiday.calendar_date - span_end).days
            else:
                distance = 0
            if nearest is None or distance < nearest[0]:
                nearest = (distance, holiday)
        if nearest is None or nearest[0] > AiHrSuggestionRepository.PRE_HOLIDAY_ADJACENCY_DAYS:
            return None
        return nearest[1]

    @classmethod
    def _plan_best_block(
        cls,
        balance_days: int,
        available: int,
        today: date,
        year_end: date,
        *,
        teammate_spans: Sequence[tuple[date, date]] = (),
        own_spans: Sequence[tuple[date, date]] = (),
        blackout_spans: Sequence[tuple[date, date]] = (),
        holidays: Sequence[Holiday] = (),
    ) -> _PlannedBlock | None:
        """Calmest usable window; forfeit-window fallback when all are blocked."""
        if balance_days <= 0 or available <= 0:
            return None
        planned = min(balance_days, cls.SUGGESTED_BLOCK_DAYS, available)
        if planned <= 0:
            return None

        base_reasons = (
            f"{balance_days} day(s) would otherwise be forfeited at year end",
            f"balance forfeits in {available} day(s)",
        )

        # 1. enumerate every usable block; eliminate conflicts up front.
        best: tuple[int, bool, int, date] | None = None
        last = year_end - timedelta(days=planned - 1)
        cursor = today
        while cursor <= last:
            block_end = cursor + timedelta(days=planned - 1)
            if cls._overlaps_any(cursor, block_end, own_spans) or cls._overlaps_any(
                cursor, block_end, blackout_spans
            ):
                cursor += timedelta(days=1)
                continue
            load = sum(
                1
                for t_start, t_end in teammate_spans
                if cls._overlaps(cursor, block_end, t_start, t_end)
            )
            adjacent_signal = cls._holiday_adjacent(cursor, block_end, holidays)
            rank: tuple[int, bool, int, date] = (
                load,
                adjacent_signal is None,  # a holiday-aligned block ranks first
                -cursor.toordinal(),  # recency wins ties (spend near year end)
                cursor,
            )
            if best is None or rank < best:
                best = rank
            cursor += timedelta(days=1)

        if best is not None:
            _, _, _, start = best
            end = start + timedelta(days=planned - 1)
            load = sum(
                1 for t_start, t_end in teammate_spans if cls._overlaps(start, end, t_start, t_end)
            )
            adjacent = cls._holiday_adjacent(start, end, holidays)
            reasons = list(base_reasons)
            if blackout_spans:
                reasons.append("clear of the current department/org leave blackout window(s)")
            if adjacent is not None:
                reasons.append(f"aligned with {adjacent.name} ({adjacent.calendar_date})")
            team_phrase = "no teammates" if load == 0 else f"{load} teammate(s)"
            reasons.append(f"{team_phrase} on leave in this window ({start} to {end})")
            return _PlannedBlock(start, end, planned, tuple(reasons))

        # 2. fallback: the forfeit window may sit inside a blackout, but the
        #    balance is forfeiting regardless — say so explicitly.
        forfeit = cls._plan_block(balance_days, available, today, year_end)
        if forfeit is None:
            return None
        start, end, days = forfeit
        reasons = list(base_reasons)
        reasons.append("only remaining window before forfeiture; may overlap a leave blackout")
        return _PlannedBlock(start, end, days, tuple(reasons))

    @staticmethod
    def _plan_block(
        balance_days: int,
        available: int,
        today: date,
        year_end: date,
    ) -> tuple[date, date, int] | None:
        """Latest usable block that fits in the remaining window (pure)."""
        if balance_days <= 0 or available <= 0:
            return None
        planned = min(balance_days, AiHrSuggestionRepository.SUGGESTED_BLOCK_DAYS, available)
        if planned <= 0:
            return None
        start_date = year_end - timedelta(days=planned - 1)
        if start_date < today:
            return None  # too late in the window to suggest a usable block
        return start_date, year_end, planned

    # -- persistence ----------------------------------------------------------

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        stmt = select(func.max(LeaveSuggestionModel.created_at)).where(
            LeaveSuggestionModel.tenant_id == tenant_id,
            LeaveSuggestionModel.status == _PENDING,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def replace_pending_suggestions(
        self, tenant_id: uuid.UUID, rows: list[LeaveSuggestion]
    ) -> None:
        """Replace only ``pending`` suggestions; keep used/dismissed history."""
        await self.session.execute(
            delete(LeaveSuggestionModel).where(
                LeaveSuggestionModel.tenant_id == tenant_id,
                LeaveSuggestionModel.status == _PENDING,
            )
        )
        if not rows:
            return
        values = [
            {
                "tenant_id": tenant_id,
                "employee_id": a.employee_id,
                "leave_type": a.leave_type,
                "start_date": a.start_date,
                "end_date": a.end_date,
                "days": a.days,
                "reasons": a.reasons,
                "created_at": a.created_at,
            }
            for a in rows
        ]
        await self.session.execute(insert(LeaveSuggestionModel), values)

    async def set_status(
        self,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        status: str,
    ) -> bool:
        """Record a prefill selection (``used``) or opt-out (``dismissed``)."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(LeaveSuggestionModel)
            .where(
                LeaveSuggestionModel.tenant_id == tenant_id,
                LeaveSuggestionModel.id == suggestion_id,
                LeaveSuggestionModel.status == _PENDING,
            )
            .values(status=status, used_at=now)
        )
        return bool((cast("CursorResult[Any]", result)).rowcount)

    # -- reads ----------------------------------------------------------------

    async def list_suggestions(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[LeaveSuggestion]:
        stmt = (
            select(
                LeaveSuggestionModel.id,
                LeaveSuggestionModel.employee_id,
                LeaveSuggestionModel.leave_type,
                LeaveSuggestionModel.start_date,
                LeaveSuggestionModel.end_date,
                LeaveSuggestionModel.days,
                LeaveSuggestionModel.reasons,
                LeaveSuggestionModel.status,
                LeaveSuggestionModel.used_at,
                LeaveSuggestionModel.created_at,
                EmployeeModel.employee_number,
                EmployeeModel.first_name,
                EmployeeModel.last_name,
                DepartmentModel.name.label("department_name"),
            )
            .join(
                EmployeeModel,
                and_(
                    EmployeeModel.tenant_id == LeaveSuggestionModel.tenant_id,
                    EmployeeModel.id == LeaveSuggestionModel.employee_id,
                ),
            )
            .outerjoin(
                DepartmentModel,
                and_(
                    DepartmentModel.tenant_id == EmployeeModel.tenant_id,
                    DepartmentModel.id == EmployeeModel.department_id,
                ),
            )
            .where(LeaveSuggestionModel.tenant_id == tenant_id)
            .order_by(LeaveSuggestionModel.created_at.desc(), LeaveSuggestionModel.id)
        )
        if employee_id is not None:
            stmt = stmt.where(LeaveSuggestionModel.employee_id == employee_id)
        rows = (await self.session.execute(stmt)).all()
        return [
            LeaveSuggestion(
                suggestion_id=r.id,
                employee_id=r.employee_id,
                leave_type=r.leave_type,
                start_date=r.start_date,
                end_date=r.end_date,
                days=r.days,
                reasons=r.reasons,
                status=r.status,
                used_at=r.used_at,
                created_at=r.created_at,
                employee_number=r.employee_number,
                first_name=r.first_name,
                last_name=r.last_name,
                department_name=r.department_name,
            )
            for r in rows
        ]

    SUGGESTED_BLOCK_DAYS = 14
    PRE_HOLIDAY_ADJACENCY_DAYS = 2


__all__ = ["AiHrSuggestionRepository", "LeaveSuggestion"]
