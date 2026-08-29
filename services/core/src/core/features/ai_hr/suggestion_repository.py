"""Smart leave-window suggestion repository (HR-AI-002, 8.2.4).

Consumes the forfeit-risk utilization alerts (8.1.4) and turns each into a
suggestion to spend accrued leave before the year-end window closes. The
suggested block is capped at ``SUGGESTED_BLOCK_DAYS`` (14) and slides to the
latest usable window (end Sunday on Dec 31). Suggestions NEVER auto-submit —
the portal prefill is recorded as ``used`` by a separate action. Per scan only
``pending`` suggestions are replaced; ``used``/``dismissed`` rows are kept as
lifecycle history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.ai_hr.models.leave_suggestion import LeaveSuggestionModel
from core.features.ai_hr.models.utilization_alert import UtilizationAlertModel
from core.features.hr.models.department import DepartmentModel
from core.features.hr.models.employee import EmployeeModel, EmploymentStatus

_ACTIVE = (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE)
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


class AiHrSuggestionRepository:
    """Read/write access to leave-window suggestions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- suggestion projection -------------------------------------------------

    async def build_suggestion_rows(self, tenant_id: uuid.UUID) -> list[LeaveSuggestion]:
        """Derive suggestions from open forfeit-risk utilization alerts."""
        today = date.today()
        year_end = date(today.year, 12, 31)

        stmt = (
            select(
                UtilizationAlertModel.employee_id,
                UtilizationAlertModel.balance_days,
                UtilizationAlertModel.days_remaining_in_year,
                UtilizationAlertModel.evidence,
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

        suggestions: list[LeaveSuggestion] = []
        for r in rows:
            balance_days = int(r.balance_days or 0)
            available = int(r.days_remaining_in_year or (year_end - today).days)
            planned_window = self._plan_block(balance_days, available, today, year_end)
            if planned_window is None:
                continue
            start_date, end_date, planned = planned_window
            evidence = cast("dict[str, Any]", r.evidence)
            suggestions.append(
                LeaveSuggestion(
                    employee_id=r.employee_id,
                    leave_type=evidence.get("leave_type") or "annual",
                    start_date=start_date,
                    end_date=end_date,
                    days=planned,
                    reasons=[
                        f"{balance_days} day(s) would otherwise be forfeited at year end",
                        f"balance forfeits in {available} day(s)",
                    ],
                )
            )
        return suggestions

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


__all__ = ["AiHrSuggestionRepository", "LeaveSuggestion"]
