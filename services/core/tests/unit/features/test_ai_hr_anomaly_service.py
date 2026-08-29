"""Unit tests for the leave-pattern anomaly detector (HR-AI-002, 8.2.1).

Covers the team-size gate Gherkin case (a <4 member team must be *abstained* —
no finding is ever persisted), the >=3x-median overuse / frequent-absence rules
with severity scaling, the two new pattern rules (short-notice Monday/Friday
and pre-holiday spike) wired through the ORM boundary, the L1 aggregate, and
the lazy-on-read TTL scan. The pure rule engine lives in skyrict_common and is
unit-tested there; these tests exercise it via the ORM repository boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from core.features.ai_hr.anomaly_repository import LeaveAnomaly
from core.features.ai_hr.anomaly_service import AnomalyService
from skyrict_common.ai_hr_rules import Holiday, RequestSignal

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.unit

TEAM = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
E1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
E2 = uuid.UUID("33333333-3333-3333-3333-333333333333")
E3 = uuid.UUID("44444444-4444-4444-4444-444444444444")
E4 = uuid.UUID("55555555-5555-5555-5555-555555555555")
TODAY = date.today()


def _sig(
    days: int,
    start: date | None = None,
    *,
    filed_on: date | None = None,
    employee_id: uuid.UUID = E1,
) -> RequestSignal:
    start = start or TODAY
    return RequestSignal(
        request_id=uuid.uuid4(),
        employee_id=employee_id,
        start_date=start,
        end_date=start + timedelta(days=days - 1),
        days=days,
        leave_type="annual",
        filed_on=filed_on or start,
    )


def _members(ids: Sequence[uuid.UUID]) -> dict[uuid.UUID | None, list[uuid.UUID]]:
    return {TEAM: list(ids)}


# -- team-size gate (Gherkin: < 4 members -> abstain) -----------------------


def test_team_size_gate_abstains_for_three_members() -> None:
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository

    requests = {E1: [_sig(30)], E2: [], E3: []}
    small = AiHrAnomalyRepository._compute(  # type: ignore[arg-type]
        {TEAM: [E1, E2, E3]}, requests, today=TODAY
    )
    assert small == []


def test_team_size_gate_passes_for_four_members() -> None:
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository

    requests = {E1: [_sig(30)], E2: [_sig(2)], E3: [_sig(2)], E4: [_sig(2)]}
    rows = AiHrAnomalyRepository._compute(  # type: ignore[arg-type]
        _members([E1, E2, E3, E4]), requests, today=TODAY
    )
    assert len(rows) == 1
    assert rows[0].anomaly_type == "leave_overuse"
    assert rows[0].team_size == 4


# -- rule behaviour ---------------------------------------------------------


def test_leave_overuse_fires_above_three_times_median() -> None:
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository

    base = TODAY - timedelta(days=30)
    requests = {
        E1: [_sig(20, base), _sig(2, base + timedelta(days=20))],
        E2: [_sig(2, base + timedelta(days=5))],
        E3: [_sig(2, base + timedelta(days=6))],
        E4: [_sig(2, base + timedelta(days=7))],
    }
    rows = AiHrAnomalyRepository._compute(  # type: ignore[arg-type]
        _members([E1, E2, E3, E4]), requests, today=TODAY
    )
    (overuse,) = [r for r in rows if r.anomaly_type == "leave_overuse"]
    assert overuse.employee_id == E1
    assert overuse.evidence["leave_days"] == 22
    assert overuse.evidence["team_median_days"] == 2.0
    assert overuse.severity == "critical"  # 22 / 2 = 11x
    assert overuse.team_size == 4


def test_frequent_absence_fires_above_three_times_median_count() -> None:
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository

    base = TODAY - timedelta(days=30)
    requests = {
        E1: [_sig(1, base + timedelta(days=i)) for i in range(8)],
        E2: [_sig(2, base + timedelta(days=5))],
        E3: [_sig(1, base + timedelta(days=6))],
        E4: [_sig(1, base + timedelta(days=7))],
    }
    rows = AiHrAnomalyRepository._compute(  # type: ignore[arg-type]
        _members([E1, E2, E3, E4]), requests, today=TODAY
    )
    (frequent,) = [r for r in rows if r.anomaly_type == "frequent_absence"]
    assert frequent.employee_id == E1
    assert frequent.evidence["request_count"] == 8
    assert frequent.evidence["team_median_count"] == 1.0


def test_no_anomaly_when_below_threshold() -> None:
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository

    base = TODAY - timedelta(days=30)
    requests = {
        E1: [_sig(4, base)],
        E2: [_sig(2, base + timedelta(days=5))],
        E3: [_sig(2, base + timedelta(days=6))],
        E4: [_sig(2, base + timedelta(days=7))],
    }
    rows = AiHrAnomalyRepository._compute(  # type: ignore[arg-type]
        _members([E1, E2, E3, E4]), requests, today=TODAY
    )
    assert rows == []


def test_ratio_severity() -> None:
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository

    assert AiHrAnomalyRepository._ratio_severity(7.0) == "critical"
    assert AiHrAnomalyRepository._ratio_severity(4.0) == "high"
    assert AiHrAnomalyRepository._ratio_severity(3.2) == "medium"
    assert AiHrAnomalyRepository._ratio_severity(40.0) == "critical"


# -- new pattern rules (Gherkin: Mon/Fri short notice, pre-holiday spike) ---


def test_short_notice_monday_friday_fires_via_repository() -> None:
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository

    monday = TODAY - timedelta(days=TODAY.weekday())  # this week's Monday
    if monday + timedelta(days=4) > TODAY:  # pragma: no cover - keep in the past
        monday -= timedelta(days=7)
    requests = {
        E1: [_sig(5, monday, filed_on=monday - timedelta(days=4))],
        E2: [_sig(1)],
        E3: [_sig(1)],
        E4: [_sig(1)],
    }
    rows = AiHrAnomalyRepository._compute(  # type: ignore[arg-type]
        _members([E1, E2, E3, E4]), requests, today=TODAY
    )
    (fired,) = [r for r in rows if r.anomaly_type == "short_notice_monday_friday"]
    assert fired.employee_id == E1
    assert fired.evidence["advance_days"] == 4
    assert fired.severity == "medium"


def test_pre_holiday_spike_fires_via_repository() -> None:
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository

    holiday = TODAY - timedelta(days=20)
    base = TODAY - timedelta(days=40)
    requests = {
        E1: [_sig(7, holiday - timedelta(days=7))],  # ends the day before
        E2: [_sig(2, base)],
        E3: [_sig(2, base + timedelta(days=1))],
        E4: [_sig(2, base + timedelta(days=2))],
    }
    rows = AiHrAnomalyRepository._compute(  # type: ignore[arg-type]
        _members([E1, E2, E3, E4]),
        requests,
        holidays=[Holiday(holiday, "Diwali", None)],
        today=TODAY,
    )
    (fired,) = [r for r in rows if r.anomaly_type == "pre_holiday_spike"]
    assert fired.employee_id == E1
    assert fired.evidence["holiday_name"] == "Diwali"
    assert fired.evidence["distance_days"] == 1
    assert fired.severity == "medium"


# -- service -----------------------------------------------------------------


def _anomaly(
    *,
    employee_id: uuid.UUID = E1,
    anomaly_type: str = "leave_overuse",
    severity: str = "medium",
) -> LeaveAnomaly:
    return LeaveAnomaly(
        employee_id=employee_id,
        anomaly_type=anomaly_type,
        severity=severity,
        title="Above-average leave consumption",
        description="30 day(s) vs a team median of 2.0.",
        team_id=TEAM,
        team_size=4,
        evidence={"leave_days": 30, "team_median_days": 2.0},
        created_at=datetime.now(UTC),
    )


class _FakeAnomalyRepo:
    def __init__(
        self,
        *,
        latest: datetime | None = None,
        rows: Sequence[LeaveAnomaly] | None = None,
        stored: Sequence[LeaveAnomaly] | None = None,
    ) -> None:
        self.latest = latest
        self.rows = rows or []
        self.stored = stored or []
        self.replacements: list[Sequence[LeaveAnomaly]] = []

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        return self.latest

    async def build_anomaly_rows(self, tenant_id: uuid.UUID) -> list[LeaveAnomaly]:
        return list(self.rows)

    async def replace_tenant_anomalies(
        self, tenant_id: uuid.UUID, rows: list[LeaveAnomaly]
    ) -> None:
        self.replacements.append(rows)
        self.stored = rows

    async def list_anomalies(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[LeaveAnomaly]:
        if employee_id is not None:
            return [a for a in self.stored if a.employee_id == employee_id]
        return list(self.stored)


async def test_org_feed_aggregates_counts_and_new_types() -> None:
    repo = _FakeAnomalyRepo(
        latest=datetime.now(UTC),
        stored=[
            _anomaly(),
            _anomaly(employee_id=E2, anomaly_type="frequent_absence", severity="high"),
            _anomaly(employee_id=E3, anomaly_type="short_notice_monday_friday"),
            _anomaly(employee_id=E4, anomaly_type="pre_holiday_spike"),
        ],
    )
    svc = AnomalyService(repo, refresh_days=7)
    summary = await svc.org_feed(TENANT)
    assert summary.total_anomalies == 4
    assert summary.by_type == {
        "leave_overuse": 1,
        "frequent_absence": 1,
        "short_notice_monday_friday": 1,
        "pre_holiday_spike": 1,
    }
    assert summary.by_severity == {"medium": 3, "high": 1}
    assert "short-notice" in summary.narrative
    assert "pre-holiday" in summary.narrative


async def test_own_and_employee_scoping() -> None:
    repo = _FakeAnomalyRepo(latest=datetime.now(UTC), stored=[_anomaly()])
    svc = AnomalyService(repo, refresh_days=7)
    assert len(await svc.own_anomalies(TENANT, E1)) == 1
    assert await svc.own_anomalies(TENANT, E2) == []
    assert len(await svc.employee_anomalies(TENANT, E1)) == 1


async def test_scan_skipped_when_fresh() -> None:
    repo = _FakeAnomalyRepo(latest=datetime.now(UTC), stored=[_anomaly()])
    await AnomalyService(repo, refresh_days=7).org_feed(TENANT)
    assert repo.replacements == []


async def test_scan_runs_when_stale_or_absent() -> None:
    stale = _FakeAnomalyRepo(latest=datetime.now(UTC) - timedelta(days=8), rows=[_anomaly()])
    await AnomalyService(stale, refresh_days=7).org_feed(TENANT)
    assert len(stale.replacements) == 1

    absent = _FakeAnomalyRepo(latest=None, rows=[_anomaly()])
    await AnomalyService(absent, refresh_days=7).org_feed(TENANT)
    assert len(absent.replacements) == 1
