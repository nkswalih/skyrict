"""Unit tests for the revenue-forecast calculator (SKY-82 A4).

The calculator is pure Decimal math - no DB. These pin the damped-trend +
seasonal-echo model, the ±1.5 sigma band from walk-forward error, MAPE
aggregation, the month-shift bookkeeping (including the calendar-year wrap),
the additive CRM pipeline uplift (SKY-82), and its per-deal health modulation
(green/yellow/red band blended with the assessment's confidence).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

from core.features.revenue_forecast.calculator import (
    Backtest,
    MonthlyRevenue,
    compute_forecast,
    deal_health_factor,
)


def _ramp_series(months: int = 12) -> list[MonthlyRevenue]:
    return [
        MonthlyRevenue(month=date(2026, m, 1), revenue=Decimal("10000") + Decimal(i * 1000))
        for i, m in enumerate(range(1, months + 1))
    ]


def _flat_series(months: int, value: str = "10000") -> list[MonthlyRevenue]:
    return [
        MonthlyRevenue(month=date(2026, m, 1), revenue=Decimal(value)) for m in range(1, months + 1)
    ]


def _year_with_peak_and_trough() -> list[MonthlyRevenue]:
    """Perfectly linear 2026 (slope 1000/month) plus a +4000 Jul peak and
    -4000 Aug trough that the seasonal echo must reproduce."""
    return [
        MonthlyRevenue(
            month=date(2026, m, 1),
            revenue=Decimal(10000 + i * 1000)
            + (Decimal("4000") if m == 7 else Decimal("-4000") if m == 8 else Decimal("0")),
        )
        for i, m in enumerate(range(1, 13))
    ]


def test_empty_history_has_no_points_and_no_backtest() -> None:
    forecast = compute_forecast([])
    assert forecast.points == ()
    assert forecast.backtest is None


def test_three_months_flat_predicts_flat_without_backtest() -> None:
    forecast = compute_forecast(_flat_series(3))
    assert len(forecast.points) == 12
    assert forecast.backtest is None
    for point in forecast.points:
        assert point.predicted == Decimal("10000")
        assert point.lower_bound is None
        assert point.upper_bound is None


def test_six_months_flat_has_points_band_and_zero_mape() -> None:
    forecast = compute_forecast(_flat_series(6))
    assert len(forecast.points) == 12
    assert forecast.backtest is not None
    assert forecast.backtest.mape == Decimal("0.0000")
    for point in forecast.points:
        assert point.predicted == Decimal("10000")
        assert point.lower_bound is not None
        assert point.upper_bound is not None
        assert point.lower_bound < point.predicted < point.upper_bound


def test_horizon_months_step_with_year_wrap() -> None:
    monthly = [
        MonthlyRevenue(month=date(2026, m, 1), revenue=Decimal("10000")) for m in range(7, 13)
    ]
    forecast = compute_forecast(monthly, horizon=3)
    months = [point.month for point in forecast.points]
    assert months == [date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1)]


def test_ramp_projects_upwards_with_damping() -> None:
    forecast = compute_forecast(_ramp_series(), horizon=12)
    backtest = forecast.backtest
    assert backtest is not None
    assert isinstance(backtest, Backtest)
    assert backtest.mape <= Decimal("0.5")  # trend fits the ramp, beating the flat baseline

    predicted = [point.predicted for point in forecast.points]
    assert all(b > a for a, b in pairwise(predicted))  # not flat, drives upward

    # Damping: the 12-month projection must stay below the extrapolated straight line.
    last_actual = Decimal("21000")
    undamped_12mo = last_actual + Decimal("12000")
    assert predicted[-1] < undamped_12mo
    for point in forecast.points:
        assert point.lower_bound is not None
        assert point.upper_bound is not None
        assert point.lower_bound < point.predicted < point.upper_bound


def test_seasonal_echo_reproduces_ups_and_downs() -> None:
    monthly = _year_with_peak_and_trough()  # 2026-01 .. 2026-12
    forecast = compute_forecast(monthly, horizon=12)

    points = forecast.points  # 2027-01 .. 2027-12
    jul = points[6]  # offset 7 -> 2027-07
    aug = points[7]  # offset 8 -> 2027-08
    assert jul.month == date(2027, 7, 1)
    assert aug.month == date(2027, 8, 1)

    # The +4000 Jul peak and -4000 Aug trough are echoed; the peak must sit
    # above its neighbour while the trough drops below it.
    assert jul.predicted > points[5].predicted
    assert aug.predicted < jul.predicted
    # The echo dominates the smoothed drift: Jul 2027 ≈ Jul 2026 peak, Aug low.
    assert (jul.predicted - aug.predicted) > Decimal("7000")


def test_band_is_minus_15_sigma_floored_at_zero() -> None:
    forecast = compute_forecast(_year_with_peak_and_trough())
    assert forecast.backtest is not None
    assert forecast.backtest.sigma is not None
    point = forecast.points[0]
    band = Decimal("1.5") * forecast.backtest.sigma
    expected_lower = max(
        Decimal("0"), (point.predicted - band).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )
    assert point.lower_bound == expected_lower
    assert point.upper_bound == (point.predicted + band).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def test_perfect_walk_forward_forecast_yields_zero_mape() -> None:
    monthly = [
        MonthlyRevenue(month=date(2026, m, 1), revenue=Decimal("10000")) for m in range(1, 10)
    ]
    forecast = compute_forecast(monthly)
    assert forecast.backtest is not None
    assert forecast.backtest.mape == Decimal("0.0000")


def test_under_three_months_history_abstains() -> None:
    for months in (0, 1, 2):
        forecast = compute_forecast(_flat_series(months))
        assert forecast.backtest is None
        assert forecast.points == ()


def test_pipeline_uplift_is_additive_only_on_forecast_months() -> None:
    monthly = _flat_series(6)  # 2026-01..06 -> horizon 2026-07..2027-06
    pipeline = {date(2026, 7, 1): Decimal("5000"), date(2027, 1, 1): Decimal("2500")}
    forecast = compute_forecast(monthly, pipeline=pipeline)

    assert forecast.points[0].predicted == Decimal("15000")  # 10000 baseline + 5000
    assert forecast.points[1].predicted == Decimal("10000")  # untouched month
    assert forecast.points[6].predicted == Decimal("12500")  # 2027-01 (year wrap) + 2500
    # Accuracy is untouched by pipeline: backtest stays the flat-line zero.
    assert forecast.backtest is not None
    assert forecast.backtest.mape == Decimal("0.0000")


def test_pipeline_breakdown_exposes_baseline_and_uplift_per_point() -> None:
    monthly = _flat_series(6)  # horizon 2026-07..2027-06
    pipeline = {date(2026, 7, 1): Decimal("5000"), date(2027, 1, 1): Decimal("2500")}
    forecast = compute_forecast(monthly, pipeline=pipeline)

    uplifted = forecast.points[0]
    assert uplifted.month == date(2026, 7, 1)
    assert uplifted.baseline == Decimal("10000")
    assert uplifted.pipeline == Decimal("5000")
    assert uplifted.predicted == uplifted.baseline + uplifted.pipeline == Decimal("15000")

    plain = forecast.points[1]
    assert plain.baseline == Decimal("10000")
    assert plain.pipeline == Decimal("0")
    assert plain.predicted == plain.baseline

    wrapped = forecast.points[6]
    assert wrapped.month == date(2027, 1, 1)
    assert wrapped.baseline == Decimal("10000")
    assert wrapped.pipeline == Decimal("2500")
    assert wrapped.predicted == wrapped.baseline + wrapped.pipeline

    # Every point carries the invariant predicted == baseline + pipeline.
    for point in forecast.points:
        assert point.predicted == point.baseline + point.pipeline


def test_baseline_and_pipeline_present_without_pipeline_input() -> None:
    forecast = compute_forecast(_flat_series(6))
    for point in forecast.points:
        assert point.baseline == Decimal("10000")
        assert point.pipeline == Decimal("0")


def test_pipeline_ignored_when_forecast_abstains() -> None:
    forecast = compute_forecast([], pipeline={date(2026, 7, 1): Decimal("5000")})
    assert forecast.points == ()
    assert forecast.backtest is None


def test_walk_forward_sample_grows_with_history() -> None:
    """Accuracy grows with months: a 4-month series is validated by one
    walk-forward error, an 8-month series by five."""
    four = compute_forecast(_flat_series(4))
    assert four.backtest is not None
    assert len(four.points) == 12
    eight = compute_forecast(_flat_series(8))
    assert eight.backtest is not None
    assert eight.backtest.mape == Decimal("0.0000")


def test_deal_health_factor_missing_or_unknown_keeps_full_weight() -> None:
    assert deal_health_factor(None, None) == Decimal("1.0000")
    assert deal_health_factor("green", None) == Decimal("1.0000")
    assert deal_health_factor("turbo", 0.9) == Decimal("1.0000")


def test_deal_health_factor_green_ignores_confidence() -> None:
    assert deal_health_factor("green", 0.9) == Decimal("1.0000")
    assert deal_health_factor("green", 0.0) == Decimal("1.0000")


def test_deal_health_factor_yellow_and_red_blend_on_confidence() -> None:
    # Full confidence -> the band discount applies as-is.
    assert deal_health_factor("yellow", 1.0) == Decimal("0.7000")
    assert deal_health_factor("red", 1.0) == Decimal("0.3500")
    # Zero confidence -> treated as a cautious guess, keep full weight.
    assert deal_health_factor("yellow", 0.0) == Decimal("1.0000")
    assert deal_health_factor("red", 0.0) == Decimal("1.0000")
    # Half confidence -> halfway between full weight and the band discount.
    assert deal_health_factor("yellow", 0.5) == Decimal("0.8500")
    assert deal_health_factor("red", 0.5) == Decimal("0.6750")


def test_deal_health_factor_clamps_confidence_out_of_range() -> None:
    assert deal_health_factor("red", 2.0) == Decimal("0.3500")
    assert deal_health_factor("red", -1.0) == Decimal("1.0000")
