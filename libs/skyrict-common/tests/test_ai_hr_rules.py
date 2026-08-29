"""Unit tests for the shared leave-pattern anomaly rules (HR-AI-002 8.2.1).

These exercise the LITERAL engine that core deploys and that the ai-agent eval
harness grades (``anomaly_precision``). They mirror the core contract the
runtime tests already assert: the team-size gate, the >=3x-median magnitude
rules, and the two new pattern rules (short-notice Monday/Friday and
pre-holiday spike) with their severity bands.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import TYPE_CHECKING

from skyrict_common.ai_hr_rules import (
    Holiday,
    RequestSignal,
    detect_leave_pattern_anomalies,
    ratio_severity,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

TEAM = uuid.UUID("11111111-1111-1111-1111-111111111111")
E1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
E2 = uuid.UUID("33333333-3333-3333-3333-333333333333")
E3 = uuid.UUID("44444444-4444-4444-4444-444444444444")
E4 = uuid.UUID("55555555-5555-5555-5555-555555555555")
TODAY = date(2026, 8, 29)


def _req(
    days: int,
    start: date,
    *,
    filed_on: date | None = None,
    employee_id: uuid.UUID = E1,
    request_id: uuid.UUID | None = None,
) -> RequestSignal:
    return RequestSignal(
        request_id=request_id or uuid.uuid4(),
        employee_id=employee_id,
        start_date=start,
        end_date=start + timedelta(days=days - 1),
        days=days,
        leave_type="annual",
        filed_on=filed_on or start,
    )


def _run(
    members: Sequence[uuid.UUID],
    requests: dict[uuid.UUID, list[RequestSignal]],
    *,
    holidays: Sequence[Holiday] = (),
    today: date = TODAY,
) -> list:
    return detect_leave_pattern_anomalies(
        members={TEAM: list(members)},
        requests_by_employee=requests,
        holidays=holidays,
        today=today,
    )


def _found(findings, anomaly_type: str):
    return [f for f in findings if f.anomaly_type == anomaly_type]


# -- team-size gate (Gherkin: < 4 members -> abstain) -------------------------


def test_team_size_gate_abstains_for_three_members() -> None:
    requests = {E1: [_req(30, TODAY - timedelta(days=10))], E2: [], E3: []}
    assert _run([E1, E2, E3], requests) == []


def test_team_size_gate_passes_for_four_members() -> None:
    base = TODAY - timedelta(days=10)
    requests = {
        E1: [_req(30, base)],
        E2: [_req(2, base + timedelta(days=5))],
        E3: [_req(2, base + timedelta(days=6))],
        E4: [_req(2, base + timedelta(days=7))],
    }
    findings = _run([E1, E2, E3, E4], requests)
    assert len(_found(findings, "leave_overuse")) == 1


# -- magnitude rules ----------------------------------------------------------


def test_leave_overuse_fires_above_three_times_median() -> None:
    base = TODAY - timedelta(days=30)
    requests = {
        E1: [_req(20, base), _req(2, base + timedelta(days=20))],
        E2: [_req(2, base + timedelta(days=5))],
        E3: [_req(2, base + timedelta(days=6))],
        E4: [_req(2, base + timedelta(days=7))],
    }
    findings = _run([E1, E2, E3, E4], requests)
    (overuse,) = _found(findings, "leave_overuse")
    assert overuse.employee_id == E1
    assert overuse.evidence["leave_days"] == 22
    assert overuse.evidence["team_median_days"] == 2.0
    assert overuse.severity == "critical"  # 22 / 2 = 11x


def test_frequent_absence_fires_above_three_times_median_count() -> None:
    base = TODAY - timedelta(days=30)
    requests = {
        E1: [_req(1, base + timedelta(days=i)) for i in range(8)],
        E2: [_req(2, base + timedelta(days=5))],
        E3: [_req(1, base + timedelta(days=6))],
        E4: [_req(1, base + timedelta(days=7))],
    }
    findings = _run([E1, E2, E3, E4], requests)
    (frequent,) = _found(findings, "frequent_absence")
    assert frequent.employee_id == E1
    assert frequent.evidence["request_count"] == 8
    assert frequent.evidence["team_median_count"] == 1.0


def test_no_anomaly_when_below_threshold() -> None:
    base = TODAY - timedelta(days=30)
    requests = {
        E1: [_req(4, base)],
        E2: [_req(2, base + timedelta(days=5))],
        E3: [_req(2, base + timedelta(days=6))],
        E4: [_req(2, base + timedelta(days=7))],
    }
    assert _run([E1, E2, E3, E4], requests) == []


def test_ratio_severity() -> None:
    assert ratio_severity(7.0) == "critical"
    assert ratio_severity(4.0) == "high"
    assert ratio_severity(3.2) == "medium"
    assert ratio_severity(40.0) == "critical"


# -- short_notice_monday_friday (Gherkin: Mon/Fri span, few days' notice) -----


def _short_notice_team_requests() -> dict[uuid.UUID, list[RequestSignal]]:
    base = TODAY - timedelta(days=20)
    friday = date(2026, 8, 14)  # a Friday inside the trailing window
    start = friday - timedelta(days=4)  # the Monday prior (2026-08-10)
    return {
        E1: [_req(5, start, filed_on=start - timedelta(days=4))],
        E2: [_req(1, base + timedelta(days=1))],
        E3: [_req(1, base + timedelta(days=2))],
        E4: [_req(1, base + timedelta(days=3))],
    }


def test_short_notice_monday_friday_fires() -> None:
    findings = _run([E1, E2, E3, E4], _short_notice_team_requests())
    (fired,) = _found(findings, "short_notice_monday_friday")
    assert fired.employee_id == E1
    assert fired.evidence["advance_days"] == 4
    assert fired.severity == "medium"  # > 3 day pressing threshold


def test_short_notice_pressing_is_high() -> None:
    requests = _short_notice_team_requests()
    rq = requests[E1][0]
    requests[E1] = [
        RequestSignal(
            request_id=rq.request_id,
            employee_id=rq.employee_id,
            start_date=rq.start_date,
            end_date=rq.end_date,
            days=rq.days,
            leave_type=rq.leave_type,
            filed_on=rq.start_date - timedelta(days=2),
        )
    ]
    findings = _run([E1, E2, E3, E4], requests)
    (fired,) = _found(findings, "short_notice_monday_friday")
    assert fired.evidence["advance_days"] == 2
    assert fired.severity == "high"


def test_short_notice_needs_a_long_block() -> None:
    requests = _short_notice_team_requests()
    rq = requests[E1][0]
    requests[E1] = [
        RequestSignal(
            request_id=rq.request_id,
            employee_id=rq.employee_id,
            start_date=rq.start_date,
            end_date=rq.start_date,
            days=1,
            leave_type=rq.leave_type,
            filed_on=rq.start_date - timedelta(days=4),
        )
    ]
    assert _found(_run([E1, E2, E3, E4], requests), "short_notice_monday_friday") == []


# -- pre_holiday_spike (Gherkin: span near a public holiday, > 3x median) -----


def _holiday_team_requests(block_start: date) -> dict[uuid.UUID, list[RequestSignal]]:
    base = TODAY - timedelta(days=20)
    return {
        E1: [_req(7, block_start)],
        E2: [_req(2, base)],
        E3: [_req(2, base + timedelta(days=1))],
        E4: [_req(2, base + timedelta(days=2))],
    }


def test_pre_holiday_spike_fires_within_adjacency() -> None:
    holiday = date(2026, 8, 11)  # remains inside the trailing window
    requests = _holiday_team_requests(date(2026, 8, 4))  # 08-04 .. 08-10
    holidays = [Holiday(holiday, "Test Day", None)]
    findings = _run([E1, E2, E3, E4], requests, holidays=holidays)
    (fired,) = _found(findings, "pre_holiday_spike")
    assert fired.employee_id == E1
    assert fired.evidence["holiday_name"] == "Test Day"
    assert fired.evidence["distance_days"] == 1  # span ends the day before holiday
    assert fired.severity == "medium"


def test_pre_holiday_spike_absent_when_far_from_holiday() -> None:
    holiday = date(2026, 8, 1)
    requests = _holiday_team_requests(date(2026, 8, 4))  # 08-04 .. 08-10
    findings = _run([E1, E2, E3, E4], requests, holidays=[Holiday(holiday, "Far", None)])
    assert _found(findings, "pre_holiday_spike") == []


def test_pre_holiday_spike_scoped_to_own_department() -> None:
    holiday = date(2026, 8, 11)
    other_dept = uuid.uuid4()
    requests = _holiday_team_requests(date(2026, 8, 4))
    findings = _run(
        [E1, E2, E3, E4],
        requests,
        holidays=[Holiday(holiday, "Other Dept Only", other_dept)],
    )
    assert _found(findings, "pre_holiday_spike") == []


def test_pre_holiday_spike_overlap_is_high() -> None:
    holiday = date(2026, 8, 11)
    requests = _holiday_team_requests(date(2026, 8, 8))  # 08-08 .. 08-14 covers 08-11
    findings = _run([E1, E2, E3, E4], requests, holidays=[Holiday(holiday, "Overlap", None)])
    (fired,) = _found(findings, "pre_holiday_spike")
    assert fired.evidence["distance_days"] == 0
    assert fired.severity == "high"
