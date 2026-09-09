"""Demo sales-order fixture coverage - every timeframe phrase must hit data.

The NL report builder turns human timeframes ("last 30 days", "last quarter")
into bind params, and the reporting engine groups by DATE(created_at). If the
fixture's days_ago spread leaves a whole band empty, a perfectly-resolved
report renders an empty table even though generate returns 200 - the exact
regression fixed here (previously every order defaulted to the seed-day
timestamp, so any historical window came back empty).

These tests assert the FIXTURE contract only; the code half (created_at
derived from days_ago, not the DB now() default) is enforced at seed time in
``seed_demo``.
"""

from __future__ import annotations

from core.domain.value_objects import OrderStatus
from core.seed_demo import SALES_ORDER_ROWS


def _eligible(row: dict[str, object]) -> bool:
    """Confirmed/fulfilled orders are the only ones the reports count."""
    return row["status"] in (OrderStatus.CONFIRMED, OrderStatus.FULFILLED)


def test_every_order_has_a_sane_recent_history_day() -> None:
    for row in SALES_ORDER_ROWS:
        days = int(str(row["days_ago"]))
        assert 1 <= days <= 365, f"days_ago out of range for {row['number']}: {days}"


def test_recent_windows_each_have_eligible_orders() -> None:
    """Every short window a user can type must hit at least one order."""
    bands: dict[str, range] = {
        "last 7 days": range(1, 8),
        "last 30 days": range(1, 31),
        "last 90 days": range(1, 91),
    }
    for band_name, days_range in bands.items():
        hits = [
            row
            for row in SALES_ORDER_ROWS
            if _eligible(row) and int(str(row["days_ago"])) in days_range
        ]
        assert hits, f"no confirmed/fulfilled order in {band_name}"


def test_last_quarter_window_has_eligible_orders() -> None:
    """The previous calendar quarter must not resolve to an empty table.

    For a seed/query on any day, the previous quarter maps to roughly
    days_ago 70-160 with the calendar arithmetic used here; the fixture must
    place eligible orders inside that band.
    """
    in_last_quarter = [
        row
        for row in SALES_ORDER_ROWS
        if _eligible(row) and int(str(row["days_ago"])) in range(70, 161)
    ]
    assert len(in_last_quarter) >= 2, "last quarter needs at least two orders"
    # Also: at least one order old enough for "last year"/"this year" prompts.
    assert any(int(str(row["days_ago"])) >= 200 for row in SALES_ORDER_ROWS), (
        "no order reaches back beyond the current year"
    )
