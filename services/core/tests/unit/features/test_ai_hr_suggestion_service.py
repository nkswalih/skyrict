"""Unit tests for the smart leave-window suggestion engine (HR-AI-002, 8.2.4).

Covers the forfeit-driven suggestion plan (pure ``_plan_block``), the L1
aggregate, self/L2 scoping, the lazy-on-read TTL scan, and the prefill/dismiss
lifecycle records (which NEVER auto-submit leave).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from core.features.ai_hr.suggestion_repository import (
    AiHrSuggestionRepository,
    LeaveSuggestion,
)
from core.features.ai_hr.suggestion_service import SuggestionService
from skyrict_common.ai_hr_rules import Holiday
from skyrict_common.exceptions import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.unit

TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
E1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
E2 = uuid.UUID("33333333-3333-3333-3333-333333333333")
SUG1 = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _suggestion(
    *,
    employee_id: uuid.UUID = E1,
    status: str = "pending",
    days: int = 14,
    suggestion_id: uuid.UUID | None = SUG1,
) -> LeaveSuggestion:
    return LeaveSuggestion(
        employee_id=employee_id,
        leave_type="annual",
        start_date=date(2026, 12, 18),
        end_date=date(2026, 12, 31),
        days=days,
        reasons=["18 day(s) would otherwise be forfeited at year end"],
        status=status,
        suggestion_id=suggestion_id,
        created_at=datetime.now(UTC),
    )


# -- plan block (pure) ---------------------------------------------------------


def test_plan_block_caps_at_suggested_size_and_slides_to_latest_window() -> None:
    block = AiHrSuggestionRepository._plan_block(
        balance_days=18, available=55, today=date(2026, 10, 1), year_end=date(2026, 12, 31)
    )
    assert block is not None
    start_date, end_date, planned = block
    assert planned == 14  # capped at SUGGESTED_BLOCK_DAYS
    assert end_date == date(2026, 12, 31)
    assert start_date == date(2026, 12, 18)
    assert (end_date - start_date).days + 1 == planned


def test_plan_block_uses_balance_when_smaller() -> None:
    block = AiHrSuggestionRepository._plan_block(
        balance_days=5, available=55, today=date(2026, 10, 1), year_end=date(2026, 12, 31)
    )
    assert block is not None
    _, end_date, planned = block
    assert planned == 5
    assert end_date == date(2026, 12, 31)


def test_plan_block_abstains_when_latest_window_already_begun() -> None:
    block = AiHrSuggestionRepository._plan_block(
        balance_days=18, available=55, today=date(2026, 12, 25), year_end=date(2026, 12, 31)
    )
    assert block is None  # 14-day block would start 12/18, before today


def test_plan_block_uses_remaining_window_when_it_shrinks() -> None:
    block = AiHrSuggestionRepository._plan_block(
        balance_days=18, available=7, today=date(2026, 12, 25), year_end=date(2026, 12, 31)
    )
    assert block is not None
    start_date, end_date, planned = block
    assert planned == 7
    assert start_date == date(2026, 12, 25)
    assert end_date == date(2026, 12, 31)


def test_plan_block_returns_none_without_balance_or_time() -> None:
    assert (
        AiHrSuggestionRepository._plan_block(0, 55, date(2026, 10, 1), date(2026, 12, 31)) is None
    )
    assert (
        AiHrSuggestionRepository._plan_block(18, 0, date(2026, 10, 1), date(2026, 12, 31)) is None
    )


# -- calendar-aware planning (team load + blackouts + holidays) ---------------


TODAY_S = date(2026, 10, 1)
YEAR_END = date(2026, 12, 31)


def _winning_block(**kwargs):
    block = AiHrSuggestionRepository._plan_best_block(18, 55, TODAY_S, YEAR_END, **kwargs)
    assert block is not None
    return block


def test_plan_best_block_defaults_to_latest_calm_window() -> None:
    block = _winning_block()
    assert (block.start_date, block.end_date, block.days) == (date(2026, 12, 18), YEAR_END, 14)
    assert any("no teammates" in r for r in block.reasons)
    assert any("forfeited" in r for r in block.reasons)


def test_plan_best_block_avoids_department_blackout() -> None:
    block = _winning_block(blackout_spans=[(date(2026, 12, 20), YEAR_END)])
    assert block.end_date < date(2026, 12, 20)  # pulled ahead of the blackout
    assert any("blackout" in r for r in block.reasons)


def test_plan_best_block_prefers_lowest_team_load() -> None:
    teammate_span = (date(2026, 12, 18), YEAR_END)
    block = _winning_block(teammate_spans=[teammate_span])
    assert block.end_date < date(2026, 12, 18)  # every NEWER window is booked
    assert any("on leave in this window" in r for r in block.reasons)


def test_plan_best_block_breaks_load_ties_toward_holiday_alignment() -> None:
    holiday = Holiday(date(2026, 12, 15), "Public Holiday", None)
    block = _winning_block(holidays=[holiday])  # Dec 17..30 sits within 2 days of it
    assert block.start_date == date(2026, 12, 17)
    assert any("aligned with Public Holiday" in r for r in block.reasons)


def test_plan_best_block_skips_windows_blocked_by_own_requests() -> None:
    own_span = (date(2026, 12, 18), YEAR_END)
    block = _winning_block(own_spans=[own_span])
    assert block.end_date < date(2026, 12, 18)


def test_plan_best_block_falls_back_to_forfeit_window_when_fully_blacked_out() -> None:
    block = _winning_block(blackout_spans=[(date(2026, 3, 1), YEAR_END)])
    assert (block.start_date, block.end_date, block.days) == (date(2026, 12, 18), YEAR_END, 14)
    assert any("may overlap a leave blackout" in r for r in block.reasons)


# -- service -------------------------------------------------------------------


class _FakeSuggestionRepo:
    def __init__(
        self,
        *,
        latest: datetime | None = None,
        rows: Sequence[LeaveSuggestion] | None = None,
        stored: Sequence[LeaveSuggestion] | None = None,
    ) -> None:
        self.latest = latest
        self.rows = rows or []
        self.stored = list(stored) if stored is not None else []
        self.replacements: list[Sequence[LeaveSuggestion]] = []
        self.set_calls: list[tuple[uuid.UUID, uuid.UUID, str]] = []

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        return self.latest

    async def build_suggestion_rows(self, tenant_id: uuid.UUID) -> list[LeaveSuggestion]:
        return list(self.rows)

    async def replace_pending_suggestions(
        self, tenant_id: uuid.UUID, rows: list[LeaveSuggestion]
    ) -> None:
        self.replacements.append(rows)
        self.stored = list(rows) + [s for s in self.stored if s.status != "pending"]

    async def set_status(self, tenant_id: uuid.UUID, suggestion_id: uuid.UUID, status: str) -> bool:
        self.set_calls.append((tenant_id, suggestion_id, status))
        for i, s in enumerate(self.stored):
            if s.suggestion_id == suggestion_id and s.status == "pending":
                updated = _suggestion(
                    employee_id=s.employee_id,
                    status=status,
                    days=s.days,
                    suggestion_id=s.suggestion_id,
                )
                self.stored[i] = updated
                return True
        return False

    async def list_suggestions(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[LeaveSuggestion]:
        if employee_id is not None:
            return [s for s in self.stored if s.employee_id == employee_id]
        return list(self.stored)


async def test_org_feed_aggregates_counts() -> None:
    repo = _FakeSuggestionRepo(
        latest=datetime.now(UTC),
        stored=[_suggestion(), _suggestion(employee_id=E2, status="used")],
    )
    svc = SuggestionService(repo, refresh_days=7)
    summary = await svc.org_feed(TENANT)
    assert summary.total_suggestions == 2
    assert summary.pending == 1
    assert summary.by_leave_type == {"annual": 2}
    assert "prefill-only" in summary.narrative


async def test_own_and_employee_scoping() -> None:
    repo = _FakeSuggestionRepo(latest=datetime.now(UTC), stored=[_suggestion()])
    svc = SuggestionService(repo, refresh_days=7)
    assert len(await svc.own_suggestions(TENANT, E1)) == 1
    assert await svc.own_suggestions(TENANT, E2) == []
    assert len(await svc.employee_suggestions(TENANT, E1)) == 1


async def test_scan_skipped_when_fresh() -> None:
    repo = _FakeSuggestionRepo(latest=datetime.now(UTC), stored=[_suggestion()])
    await SuggestionService(repo, refresh_days=7).org_feed(TENANT)
    assert repo.replacements == []


async def test_scan_runs_when_stale_or_absent() -> None:
    stale = _FakeSuggestionRepo(latest=datetime.now(UTC) - timedelta(days=8), rows=[_suggestion()])
    await SuggestionService(stale, refresh_days=7).org_feed(TENANT)
    assert len(stale.replacements) == 1

    absent = _FakeSuggestionRepo(latest=None, rows=[_suggestion()])
    await SuggestionService(absent, refresh_days=7).org_feed(TENANT)
    assert len(absent.replacements) == 1


async def test_use_records_prefill_without_auto_submit() -> None:
    repo = _FakeSuggestionRepo(latest=datetime.now(UTC), stored=[_suggestion()])
    svc = SuggestionService(repo, refresh_days=7)
    used = await svc.use_suggestion(TENANT, SUG1)
    assert used.status == "used"
    assert repo.stored[0].status == "used"


async def test_dismiss_marks_status() -> None:
    repo = _FakeSuggestionRepo(latest=datetime.now(UTC), stored=[_suggestion()])
    svc = SuggestionService(repo, refresh_days=7)
    dismissed = await svc.dismiss_suggestion(TENANT, SUG1)
    assert dismissed.status == "dismissed"
    assert repo.stored[0].status == "dismissed"


async def test_mark_raises_for_unknown_or_non_pending() -> None:
    repo = _FakeSuggestionRepo(latest=datetime.now(UTC), stored=[])
    svc = SuggestionService(repo, refresh_days=7)
    with pytest.raises(NotFoundError):
        await svc.use_suggestion(TENANT, SUG1)
    with pytest.raises(NotFoundError):
        await svc.dismiss_suggestion(TENANT, uuid.uuid4())
