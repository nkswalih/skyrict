"""Unit tests for the leave-pattern anomaly detector (HR-AI-002, 8.2.1).

Covers the team-size gate Gherkin case (a <4 member team must be *abstained* —
no finding is ever persisted), the >=3x-median overuse / frequent-absence
rules with severity scaling, the L1 aggregate, and the lazy-on-read TTL scan.
The pure rule engine ``_compute`` is exercised directly; the service tests use
a fake repository.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from core.features.ai_hr.anomaly_repository import (
    AiHrAnomalyRepository,
    LeaveAnomaly,
)
from core.features.ai_hr.anomaly_service import AnomalyService

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.unit

TEAM = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
E1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
E2 = uuid.UUID("33333333-3333-3333-3333-333333333333")
E3 = uuid.UUID("44444444-4444-4444-4444-444444444444")
E4 = uuid.UUID("55555555-5555-5555-5555-555555555555")


def _req(days: int, start: date | None = None) -> SimpleNamespace:
    return SimpleNamespace(days=days, start_date=start or date.today())


def _members(ids: Sequence[uuid.UUID]) -> dict[uuid.UUID | None, list[uuid.UUID]]:
    return {TEAM: list(ids)}


# -- team-size gate (Gherkin: < 4 members -> abstain) -----------------------


def test_team_size_gate_abstains_for_three_members() -> None:
    requests = {E1: [_req(30)], E2: [_req(1)], E3: [_req(1)]}
    small = AiHrAnomalyRepository._compute({TEAM: [E1, E2, E3]}, requests)
    assert small == []


def test_team_size_gate_passes_for_four_members() -> None:
    requests = {E1: [_req(30)], E2: [_req(2)], E3: [_req(2)], E4: [_req(2)]}
    rows = AiHrAnomalyRepository._compute(_members([E1, E2, E3, E4]), requests)
    assert len(rows) == 1
    assert rows[0].anomaly_type == "leave_overuse"
    assert rows[0].team_size == 4


# -- rule behaviour ----------------------------------------------------------


def test_leave_overuse_fires_above_three_times_median() -> None:
    requests = {
        E1: [_req(20), _req(2)],
        E2: [_req(2)],
        E3: [_req(2)],
        E4: [_req(2)],
    }
    rows = AiHrAnomalyRepository._compute(_members([E1, E2, E3, E4]), requests)
    (overuse,) = [r for r in rows if r.anomaly_type == "leave_overuse"]
    assert overuse.employee_id == E1
    assert overuse.evidence["leave_days"] == 22
    assert overuse.evidence["team_median_days"] == 2.0
    assert overuse.severity == "critical"  # 22 / 2 = 11x
    assert overuse.team_size == 4


def test_frequent_absence_fires_above_three_times_median_count() -> None:
    requests = {
        E1: [_req(1) for _ in range(8)],
        E2: [_req(2)],
        E3: [_req(1)],
        E4: [_req(1)],
    }
    rows = AiHrAnomalyRepository._compute(_members([E1, E2, E3, E4]), requests)
    (frequent,) = [r for r in rows if r.anomaly_type == "frequent_absence"]
    assert frequent.employee_id == E1
    assert frequent.evidence["request_count"] == 8
    assert frequent.evidence["team_median_count"] == 1.0


def test_no_anomaly_when_below_threshold() -> None:
    requests = {E1: [_req(4)], E2: [_req(2)], E3: [_req(2)], E4: [_req(2)]}
    rows = AiHrAnomalyRepository._compute(_members([E1, E2, E3, E4]), requests)
    assert rows == []


def test_ratio_severity() -> None:
    assert AiHrAnomalyRepository._ratio_severity(7.0) == "critical"
    assert AiHrAnomalyRepository._ratio_severity(4.0) == "high"
    assert AiHrAnomalyRepository._ratio_severity(3.2) == "medium"
    assert AiHrAnomalyRepository._ratio_severity(40.0) == "critical"


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


async def test_org_feed_aggregates_counts() -> None:
    repo = _FakeAnomalyRepo(
        latest=datetime.now(UTC),
        stored=[
            _anomaly(),
            _anomaly(employee_id=E2, anomaly_type="frequent_absence", severity="high"),
        ],
    )
    svc = AnomalyService(repo, refresh_days=7)
    summary = await svc.org_feed(TENANT)
    assert summary.total_anomalies == 2
    assert summary.by_type == {"leave_overuse": 1, "frequent_absence": 1}
    assert summary.by_severity == {"medium": 1, "high": 1}
    assert "overuse" in summary.narrative


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
