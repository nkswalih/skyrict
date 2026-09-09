"""Resolve a report spec's filters/timeframe into the template's bind params.

The LLM only ever produces human-readable ``filters``/``timeframe`` intent; it
never picks a parameter name or raw date. This module deterministically turns
that intent into the template's DECLARED bind parameters (Core Phase-1 reports
take exactly ``tenant_id`` plus ISO dates: ``from_date``/``to_date`` for period
reports, ``as_of_date`` for point-in-time reports).

The ``timeframe`` phrases this understands are deliberately small and exact -
anything unrecognized is rejected (clarification upstream) rather than guessed,
so no report is ever run on a date the user did not clearly request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_agent.features.report_builder.gateway import ReportDefinition


@dataclass(frozen=True, slots=True)
class ParamResolution:
    """Outcome of turning the intent into declared bind params."""

    params: dict[str, Any]
    """
    Resolved bind values for the template's declared params. ``tenant_id`` is
    filled by the engine (server-authoritative); only ``from_date``/``to_date``
    /``as_of_date`` style date binds are produced here.
    """


@dataclass(frozen=True, slots=True)
class TimeframeOutcome:
    """A recognized timeframe band or a request to clarify."""

    kind: str  # "resolved" | "unresolved"
    reason: str = ""
    from_date: date | None = None
    to_date: date | None = None
    as_of_date: date | None = None


# Recognized timeframe phrases, mapped to relative bands relative to today.
_MONTHLY_NAMED = {
    "last month": ("month", -1),
    "this month": ("month", 0),
    "last quarter": ("quarter", -1),
    "this quarter": ("quarter", 0),
    "last year": ("year", -1),
    "this year": ("year", 0),
    "last 7 days": ("days", -7),
    "last 14 days": ("days", -14),
    "last 30 days": ("days", -30),
    "last 90 days": ("days", -90),
}


def resolve_timeframe(timeframe: str | None, *, today: date | None = None) -> TimeframeOutcome:
    """Map a human timeframe phrase to concrete from/to (or as-of) dates.

    As-of phrases resolve to a single ``as_of_date`` (point-in-time reports);
    range phrases resolve to ``from_date``/``to_date``. Unrecognized phrases
    return ``unresolved`` so the engine can ask for clarity instead of guessing.
    """
    if timeframe is None or not timeframe.strip():
        return TimeframeOutcome(kind="unresolved", reason="Please provide a time period.")
    phrase = " ".join(timeframe.strip().lower().split())
    ref = today or datetime.now(UTC).date()

    if phrase.startswith("as of "):
        as_of = _parse_iso_date(phrase.removeprefix("as of ").strip())
        if as_of is None:
            return TimeframeOutcome(
                kind="unresolved",
                reason="I need a clear date - try 'as of 2026-08-31'.",
            )
        return TimeframeOutcome(kind="resolved", as_of_date=as_of)

    named = _MONTHLY_NAMED.get(phrase)
    if named is not None:
        granularity, offset = named
        start = _start_of_period(ref, granularity, offset)
        end = ref if granularity in ("days",) else _end_of_period(ref, granularity, offset)
        return TimeframeOutcome(kind="resolved", from_date=start, to_date=end)

    iso_from = _parse_iso_date(phrase.split(" to ")[0])
    if iso_from is not None and " to " in phrase:
        iso_to = _parse_iso_date(phrase.split(" to ")[1])
        if iso_to is not None:
            return TimeframeOutcome(kind="resolved", from_date=iso_from, to_date=iso_to)

    return TimeframeOutcome(
        kind="unresolved",
        reason=(
            "I couldn't understand that time period. Try 'last month', "
            "'last quarter', 'last 30 days', '2026-08-01 to 2026-08-31', "
            "or 'as of 2026-08-31'."
        ),
    )


def build_report_params(
    *,
    definition: ReportDefinition,
    timeframe: str | None,
    today: date | None = None,
) -> ParamResolution | TimeframeOutcome:
    """Build the template's declared bind params from the timeframe intent.

    Returns a :class:`ParamResolution` when the template's date params are
    satisfiable, or a ``unresolved`` :class:`TimeframeOutcome` for the engine
    to raise as a clarification. ``tenant_id`` is intentionally NOT set here -
    the engine adds it from the authenticated request.
    """
    declared = set(definition.params)
    # Point-in-time templates (e.g. headcount by department) declare only
    # tenant_id - a timeframe is NOT meaningful there and must not be
    # required. The LLM correctly emits timeframe: null for them; demanding a
    # period would turn a valid prompt into a fake clarification.
    date_params = declared & {"from_date", "to_date", "as_of_date"}
    if not date_params:
        return ParamResolution(params={})

    outcome = resolve_timeframe(timeframe, today=today)
    if outcome.kind != "resolved":
        return outcome

    params: dict[str, Any] = {}
    if "from_date" in declared and "to_date" in declared:
        if outcome.from_date is None or outcome.to_date is None:
            return TimeframeOutcome(
                kind="unresolved",
                reason="That report needs a from-to date range.",
            )
        params["from_date"] = outcome.from_date.isoformat()
        params["to_date"] = outcome.to_date.isoformat()
    elif "as_of_date" in declared:
        if outcome.as_of_date is None:
            return TimeframeOutcome(
                kind="unresolved",
                reason="That report needs a single 'as of' date.",
            )
        params["as_of_date"] = outcome.as_of_date.isoformat()
    else:
        # No date params on the template - nothing to resolve. The engine
        # treats any non-ParamResolution return as a clarification, so an
        # empty resolution keeps a no-date template runnable.
        return ParamResolution(params={})
    return ParamResolution(params=params)


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _start_of_period(ref: date, granularity: str, offset: int) -> date:
    if granularity == "days":
        return ref + timedelta(days=offset)
    first = date(ref.year, ref.month, 1)
    if granularity == "month":
        return _shift_month(first, offset)
    if granularity == "quarter":
        quarter_start_month = ((ref.month - 1) // 3) * 3 + 1
        return _shift_month(date(ref.year, quarter_start_month, 1), offset * 3)
    # year
    return date(ref.year + offset, 1, 1)


def _end_of_period(ref: date, granularity: str, offset: int) -> date:
    """Last day of the shifted period (``days`` bands end at ``ref``)."""
    if granularity == "days":
        return ref
    start = _start_of_period(ref, granularity, offset)
    period_months = {"month": 1, "quarter": 3, "year": 12}[granularity]
    return _last_day_of_month(start.year, start.month + period_months - 1)


def _shift_month(first_of_month: date, offset: int) -> date:
    """Shift a first-of-month date by ``offset`` months (wraps years)."""
    month_index = first_of_month.year * 12 + (first_of_month.month - 1) + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)
