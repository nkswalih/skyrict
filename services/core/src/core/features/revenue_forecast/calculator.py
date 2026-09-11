"""Revenue forecasting (SKY-82 A4) - pure forecasting math.

The method is a **damped linear trend plus a monthly seasonal echo** over a
12-month horizon, with a confidence band of ±1.5 sigma of the walk-forward
historical error distribution. Instead of a flat moving average, the model

- fits a least-squares trend to the recognised-revenue series and projects it
  forward with **damping** (each month's increment shrinks by ``TREND_DAMPING``,
  so the projection curves toward a plateau rather than over-extrapolating),
- adds a **seasonal echo**: for each of the 12 calendar months already seen,
  the average deviation from the trend line is added back to the projected
  month with the same calendar month. This reproduces the observed ups and
  downs (promotion months, quarter-end spikes, seasonality) in the horizon.
  Calendar months never yet observed get no adjustment.

The forecast abstains (empty point set) when there is fewer than 3 months of
recognized revenue, per the FIN-AI-003 guardrail. Accuracy grows with data:
each new month adds one walk-forward error to the sample backing the sigma
band and MAPE, and the seasonal echo stabilises once a calendar month has been
observed more than once.

Pipeline weighting (SKY-82): each forecast month may also carry an additive
CRM pipeline uplift. ``compute_forecast`` accepts a ``pipeline`` map of
forecast-month -> expected revenue from open deals (weighted conversion value
= per-deal ``probability/100 x amount``, bucketed by ``expected_close_date``).
The uplift only touches the projected months - the backtest, MAPE, and sigma
band are computed over historical months only, so pipeline data can never
inflate the model's reported accuracy. The per-deal conversion weight may be
modulated by the ai-agent's deal-health engine (:func:`deal_health_factor`):
a green deal keeps its full weight, a yellow or red deal is discounted to its
band factor, and the discount is blended toward neutral by low confidence (a
cautious assessment never cuts a deal as hard as a confident one).
All arithmetic is :class:`decimal.Decimal` so figures round-trip exactly
through the SQL ``Numeric`` columns and the web UI.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MODEL_VERSION = "trend-seasonal"
TREND_DAMPING = Decimal("0.90")
BACKTEST_MIN_POINTS = 3
MIN_HISTORY_MONTHS = 3
HORIZON_MONTHS = 12
BAND_SIGMA_MULTIPLIER = Decimal("1.5")

# Conversion-weight discount per deal-health band (SKY-82 A4): healthy deals
# keep full weight; flagged deals are discounted by their band.
# ``ai_deal_health.health`` is ``green | yellow | red`` (ai-agent schema).
DEAL_HEALTH_FACTORS: dict[str, Decimal] = {
    "green": Decimal("1.0000"),
    "yellow": Decimal("0.7000"),
    "red": Decimal("0.3500"),
}


@dataclass(frozen=True)
class MonthlyRevenue:
    """Recognized revenue for one calendar month (from approved invoices)."""

    month: date
    revenue: Decimal


@dataclass(frozen=True)
class ForecastPoint:
    month: date
    baseline: Decimal  # damped trend + seasonal echo (invoice-based projection)
    pipeline: Decimal  # weighted CRM pipeline uplift blended into this month
    predicted: Decimal  # == baseline + pipeline
    lower_bound: Decimal | None
    upper_bound: Decimal | None


@dataclass(frozen=True)
class Backtest:
    mape: Decimal
    sigma: Decimal | None  # None when there are no errors (perfect, or too little history)


@dataclass(frozen=True)
class Forecast:
    points: tuple[ForecastPoint, ...]
    backtest: Backtest | None
    model_version: str = MODEL_VERSION


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def deal_health_factor(health: str | None, confidence: float | None) -> Decimal:
    """Conversion-weight multiplier for one deal from its latest health rating.

    A deal's weighted pipeline value is its conversion probability scaled by
    this factor: green keeps the full weight (1.0), yellow is discounted to
    ``DEAL_HEALTH_FACTORS`` and red further still. The band factor is blended
    toward neutral by ``confidence`` - a rating the engine is unsure about
    (low confidence) moves the multiplier back toward 1.0, so a cautious
    assessment never cuts a deal as hard as a confident one. Deals with no
    assessment yet keep their full weight.
    """
    band = DEAL_HEALTH_FACTORS.get(health or "", Decimal("1.0000"))
    if confidence is None:
        return band
    clamped = max(0.0, min(1.0, confidence))
    blended = 1 - (1 - float(band)) * clamped
    return _quantize(Decimal(str(blended)))


def month_step(month: date, offset_months: int) -> date:
    """The first-of-month ``offset_months`` after ``month`` (calendar-year wrap)."""
    year = month.year + (month.month - 1 + offset_months) // 12
    m = (month.month - 1 + offset_months) % 12 + 1
    return date(year, m, 1)


def _ols(values: list[Decimal]) -> tuple[float, float]:
    """Least-squares intercept/slope on positions 1..n (n >= 2)."""
    n = len(values)
    xs = list(range(1, n + 1))
    ys = [float(v) for v in values]
    x_bar = sum(xs) / n
    y_bar = sum(ys) / n
    s_xx = sum((x - x_bar) ** 2 for x in xs)
    s_xy = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys, strict=True))
    slope = s_xy / s_xx if s_xx else 0.0
    return y_bar - slope * x_bar, slope


def _trend_at(intercept: float, slope: float, position: int) -> float:
    """Trend-line value at 1-based ``position``."""
    return intercept + slope * position


def _damping_factor(offset: int) -> float:
    """Cumulative damped drift weight: ``phi + phi**2 + ... + phi**offset``."""
    phi = float(TREND_DAMPING)
    total = 0.0
    power = 1.0
    for _ in range(offset):
        power *= phi
        total += power
    return total


def _seasonal_factors(
    monthly: list[MonthlyRevenue], intercept: float, slope: float
) -> dict[int, Decimal]:
    """Average deviation from the trend for each observed calendar month."""
    acc: dict[int, list[Decimal]] = {}
    for index, point in enumerate(monthly, start=1):
        trend = Decimal(str(_trend_at(intercept, slope, index)))
        acc.setdefault(point.month.month, []).append(point.revenue - trend)
    return {month: _quantize(sum(values) / Decimal(len(values))) for month, values in acc.items()}


def backtest_errors(monthly: list[MonthlyRevenue]) -> list[Decimal]:
    """Walk-forward prediction errors (predicted - actual).

    For each month ``t >= BACKTEST_MIN_POINTS`` fit the trend + seasonal echo
    over the ``t`` prior months, predict month ``t`` with the same model, and
    record the signed error. Errors start at month 4 and the sample (hence the
    band/MAPE confidence) grows as more history accrues. Returns [] when there
    is too little history to validate.
    """
    errors: list[Decimal] = []
    for t in range(BACKTEST_MIN_POINTS, len(monthly)):
        window = monthly[:t]
        intercept, slope = _ols([point.revenue for point in window])
        seasonal = _seasonal_factors(window, intercept, slope)
        calendar = monthly[t].month.month
        predicted = Decimal(str(_trend_at(intercept, slope, t + 1))) + seasonal.get(
            calendar, Decimal("0")
        )
        errors.append(predicted - monthly[t].revenue)
    return errors


def _mape(errors: list[Decimal], actuals: list[Decimal]) -> Decimal:
    aligned = [(abs(e), a) for e, a in zip(errors, actuals, strict=True) if a > 0]
    if not aligned:
        return Decimal("0")
    total_absolute = sum((e for e, _ in aligned), Decimal("0"))
    total_actual = sum((a for _, a in aligned), Decimal("0"))
    return _quantize(total_absolute / total_actual * Decimal("100"))


def compute_forecast(
    monthly: list[MonthlyRevenue],
    *,
    horizon: int = HORIZON_MONTHS,
    pipeline: Mapping[date, Decimal] | None = None,
) -> Forecast:
    """Forecast ``horizon`` months ahead using a damped trend + seasonal echo.

    History is expected to be a contiguous, ascending monthly series. With
    fewer than :data:`MIN_HISTORY_MONTHS` months the model abstains and returns
    an empty point set (per the FIN-AI-003 guardrail). With at least one
    walk-forward error the points carry a ``± 1.5 sigma`` band (of the signed
    historical errors, floored at zero); otherwise ``backtest`` is None and the
    points carry no band. The projection curves toward a plateau (damping) and
    echoes the observed per-calendar-month ups and downs, so it is not a flat
    line.

    ``pipeline`` optionally maps a forecast month to a weighted expected
    pipeline value (see the module docstring); the value is added to that
    month's prediction on top of the trend + seasonal baseline. The backtest,
    MAPE, and sigma band are computed over historical months only, so pipeline
    input never influences the reported accuracy.

    Each point carries its decomposition: ``baseline`` (the trend + seasonal
    projection alone) and ``pipeline`` (the uplift blended in), with
    ``predicted == baseline + pipeline`` exactly - so callers can show *why* a
    month is high.
    """
    if len(monthly) < MIN_HISTORY_MONTHS:
        return Forecast(points=(), backtest=None)

    errors = backtest_errors(monthly)
    backtest: Backtest | None = None
    if errors:
        sigma = max(Decimal("0.0001"), _stddev(errors))
        backtest = Backtest(
            mape=_mape(errors, [point.revenue for point in monthly[BACKTEST_MIN_POINTS:]]),
            sigma=sigma,
        )

    intercept, slope = _ols([point.revenue for point in monthly])
    seasonal = _seasonal_factors(monthly, intercept, slope)
    base = _trend_at(intercept, slope, len(monthly))
    last_month = monthly[-1].month
    pipeline = pipeline or {}

    points: list[ForecastPoint] = []
    for offset in range(1, horizon + 1):
        forecast_month = month_step(last_month, offset)
        drift = slope * _damping_factor(offset)
        baseline_value = _quantize(
            Decimal(str(base + drift)) + seasonal.get(forecast_month.month, Decimal("0"))
        )
        pipe = _quantize(pipeline.get(forecast_month, Decimal("0")))
        predicted = _quantize(baseline_value + pipe)
        lower: Decimal | None
        upper: Decimal | None
        if backtest is not None:
            assert backtest.sigma is not None
            band = BAND_SIGMA_MULTIPLIER * backtest.sigma
            lower = max(Decimal("0"), predicted - band)
            upper = predicted + band
        else:
            lower = upper = None
        points.append(
            ForecastPoint(
                month=forecast_month,
                baseline=baseline_value,
                pipeline=pipe,
                predicted=predicted,
                lower_bound=_quantize(lower) if lower is not None else None,
                upper_bound=_quantize(upper) if upper is not None else None,
            )
        )
    return Forecast(points=tuple(points), backtest=backtest)


def _stddev(values: list[Decimal]) -> Decimal:
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum(((value - mean) ** 2 for value in values), Decimal("0")) / Decimal(len(values))
    return variance.sqrt()
