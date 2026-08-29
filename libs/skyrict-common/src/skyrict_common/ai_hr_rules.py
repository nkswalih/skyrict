"""Pure leave-pattern anomaly rules shared by core and the eval harness.

HR-AI-002 §8.2.1 — the leave-pattern anomaly inbox.  This module is pure
(no SQLAlchemy, no I/O, stdlib only) so that the engine deployed in
:mod:`core.features.ai_hr.anomaly_repository` and the ai-agent eval harness
(``anomaly_precision``, SKY-72) run the LITERAL same detection code.

Every rule is gated by a *team-size gate*: a team with fewer than
``min_team_size`` active members is abstained entirely (thin baselines never
emit findings), and the median-comparison rules also require the team median
to be measurable:

- ``leave_overuse``: an employee's trailing total leave days >= ``spike_ratio``
  x the team median days (median >= 1).
- ``frequent_absence``: an employee's request count >= ``spike_ratio`` x the
  team median count (median >= 1).
- ``short_notice_monday_friday``: one request whose span touches a Monday or
  Friday, was filed fewer than ``short_notice_days`` before it starts, AND is
  at ``spike_ratio`` x the team median days.
- ``pre_holiday_spike``: one request whose span sits within
  ``pre_holiday_adjacency_days`` of a public holiday (org-wide or scoped to the
  team's department) AND is at ``spike_ratio`` x the team median days.

Severity scaling: overuse/frequent use the ratio bands (>= 5 critical,
>= 4 high, else medium); short-notice is high when filed within
``short_notice_pressing_days``; pre-holiday is high when the request overlaps
the holiday date, else medium.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping, Sequence

_FINDING_TITLES: dict[str, str] = {
    "leave_overuse": "Above-average leave consumption",
    "frequent_absence": "Frequent leave requests",
    "short_notice_monday_friday": "Short-notice leave on a Monday/Friday",
    "pre_holiday_spike": "Leave clustered around a public holiday",
}


@dataclass(frozen=True, slots=True)
class RequestSignal:
    """One leave request as the rules see it (projected from the ORM row)."""

    request_id: uuid.UUID
    employee_id: uuid.UUID
    start_date: date
    end_date: date
    days: int
    leave_type: str
    filed_on: date


@dataclass(frozen=True, slots=True)
class Holiday:
    """One public holiday / office-closure day (or department-scoped)."""

    calendar_date: date
    name: str
    department_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class AnomalyFinding:
    """One computed finding; the ORM layer maps this onto its row shape."""

    employee_id: uuid.UUID
    anomaly_type: str
    severity: str
    title: str
    description: str
    team_id: uuid.UUID | None
    team_size: int
    evidence: dict[str, Any] = field(default_factory=dict)


def ratio_severity(ratio: float) -> str:
    """Map a ratio to the documented severity band."""
    if ratio >= 5:
        return "critical"
    if ratio >= 4:
        return "high"
    return "medium"


def _distance_to_span(span_start: date, span_end: date, day: date) -> int:
    """Minimum day distance from ``day`` to the inclusive span ``[start, end]``."""
    if day < span_start:
        return (span_start - day).days
    if day > span_end:
        return (day - span_end).days
    return 0


def detect_leave_pattern_anomalies(
    *,
    members: Mapping[uuid.UUID | None, Sequence[uuid.UUID]],
    requests_by_employee: Mapping[uuid.UUID, Sequence[RequestSignal]],
    holidays: Sequence[Holiday] = (),
    today: date,
    trailing_days: int = 90,
    min_team_size: int = 4,
    spike_ratio: float = 3.0,
    short_notice_days: int = 14,
    short_notice_pressing_days: int = 3,
    pre_holiday_adjacency_days: int = 2,
) -> list[AnomalyFinding]:
    """Run every rule over one tenant's teams and return the findings.

    ``members`` groups active employees by department; ``requests`` maps each
    employee to their requests (only approved/pending need be passed, but the
    engine re-filters to the trailing window so callers can pass more). Inputs
    are immutable (read-only); the caller owns persistence.
    """
    window_start = today - timedelta(days=trailing_days)
    findings: list[AnomalyFinding] = []

    for team_id, member_ids in members.items():
        if len(member_ids) < min_team_size:
            continue  # team-size gate: abstain for thin baselines
        team_holidays = [
            h for h in holidays if h.department_id is None or h.department_id == team_id
        ]

        days_by: dict[uuid.UUID, int] = {}
        count_by: dict[uuid.UUID, int] = {}
        windowed: dict[uuid.UUID, list[RequestSignal]] = {}
        for mid in member_ids:
            windowed[mid] = [
                r
                for r in requests_by_employee.get(mid, ())
                if window_start <= r.start_date <= today
            ]
            days_by[mid] = sum(r.days for r in windowed[mid])
            count_by[mid] = len(windowed[mid])

        med_days = median(days_by.values())
        med_count = median(count_by.values())

        for mid in member_ids:
            member_reqs = windowed[mid]
            if not member_reqs:
                continue
            total_days = days_by[mid]
            count = count_by[mid]
            first_start = min(rq.start_date for rq in member_reqs).isoformat()

            # leave_overuse: trailing days >= 3x team median days.
            if med_days >= 1 and total_days >= spike_ratio * med_days:
                ratio = total_days / med_days
                findings.append(
                    AnomalyFinding(
                        employee_id=mid,
                        anomaly_type="leave_overuse",
                        severity=ratio_severity(ratio),
                        title=_FINDING_TITLES["leave_overuse"],
                        description=(
                            f"{total_days} leave day(s) used in the trailing "
                            f"{trailing_days} days vs a team median of "
                            f"{med_days:.1f}."
                        ),
                        team_id=team_id,
                        team_size=len(member_ids),
                        evidence={
                            "window_days": trailing_days,
                            "leave_days": total_days,
                            "team_median_days": round(med_days, 2),
                            "request_count": count,
                            "first_start": first_start,
                        },
                    )
                )

            # frequent_absence: request count >= 3x team median count.
            if med_count >= 1 and count >= spike_ratio * med_count:
                ratio = count / med_count
                findings.append(
                    AnomalyFinding(
                        employee_id=mid,
                        anomaly_type="frequent_absence",
                        severity=ratio_severity(ratio),
                        title=_FINDING_TITLES["frequent_absence"],
                        description=(
                            f"{count} leave request(s) in the trailing "
                            f"{trailing_days} days vs a team median of "
                            f"{med_count:.1f}."
                        ),
                        team_id=team_id,
                        team_size=len(member_ids),
                        evidence={
                            "window_days": trailing_days,
                            "request_count": count,
                            "team_median_count": round(med_count, 2),
                            "leave_days": total_days,
                        },
                    )
                )

            if med_days < 1:
                continue  # magnitude-based rules need a measurable median

            for rq in member_reqs:
                # short_notice_monday_friday: Mon/Fri span filed on short notice
                # and long relative to the team (a conspicuous "block").
                touches_fringe = rq.start_date.weekday() in (0, 4) or (
                    rq.end_date.weekday() in (0, 4)
                )
                advance = (rq.start_date - rq.filed_on).days
                if (
                    rq.days >= spike_ratio * med_days
                    and touches_fringe
                    and 0 <= advance < short_notice_days
                ):
                    severity = "high" if advance <= short_notice_pressing_days else "medium"
                    findings.append(
                        AnomalyFinding(
                            employee_id=mid,
                            anomaly_type="short_notice_monday_friday",
                            severity=severity,
                            title=_FINDING_TITLES["short_notice_monday_friday"],
                            description=(
                                f"Short-notice leave touching a Monday/Friday: "
                                f"{rq.days} day(s) from {rq.start_date} to "
                                f"{rq.end_date} filed {advance} day(s) ahead vs "
                                f"a team median of {med_days:.1f} day(s)."
                            ),
                            team_id=team_id,
                            team_size=len(member_ids),
                            evidence={
                                "request_id": str(rq.request_id),
                                "window_days": trailing_days,
                                "request_days": rq.days,
                                "team_median_days": round(med_days, 2),
                                "advance_days": advance,
                                "start_date": rq.start_date.isoformat(),
                                "end_date": rq.end_date.isoformat(),
                            },
                        )
                    )

                # pre_holiday_spike: span near a holiday and long vs the median.
                if rq.days >= spike_ratio * med_days and team_holidays:
                    nearest: tuple[int, Holiday] | None = None
                    for holiday in team_holidays:
                        distance = _distance_to_span(
                            rq.start_date, rq.end_date, holiday.calendar_date
                        )
                        if nearest is None or distance < nearest[0]:
                            nearest = (distance, holiday)
                    assert nearest is not None
                    distance, holiday = nearest
                    if distance <= pre_holiday_adjacency_days:
                        severity = "high" if distance == 0 else "medium"
                        findings.append(
                            AnomalyFinding(
                                employee_id=mid,
                                anomaly_type="pre_holiday_spike",
                                severity=severity,
                                title=_FINDING_TITLES["pre_holiday_spike"],
                                description=(
                                    f"Leave within {distance} day(s) of "
                                    f"{holiday.name} ({holiday.calendar_date}): "
                                    f"{rq.days} day(s) vs a team median of "
                                    f"{med_days:.1f}."
                                ),
                                team_id=team_id,
                                team_size=len(member_ids),
                                evidence={
                                    "request_id": str(rq.request_id),
                                    "window_days": trailing_days,
                                    "request_days": rq.days,
                                    "team_median_days": round(med_days, 2),
                                    "start_date": rq.start_date.isoformat(),
                                    "end_date": rq.end_date.isoformat(),
                                    "holiday_date": holiday.calendar_date.isoformat(),
                                    "holiday_name": holiday.name,
                                    "distance_days": distance,
                                },
                            )
                        )

    return findings


__all__ = [
    "AnomalyFinding",
    "Holiday",
    "RequestSignal",
    "detect_leave_pattern_anomalies",
    "ratio_severity",
]
