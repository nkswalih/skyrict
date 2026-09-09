"""Unit tests for timeframe -> bind-param resolution (report builder, SKY-80)."""

from __future__ import annotations

from datetime import date

from ai_agent.features.report_builder.gateway import ReportDefinition
from ai_agent.features.report_builder.params import (
    ParamResolution,
    TimeframeOutcome,
    build_report_params,
    resolve_timeframe,
)

TODAY = date(2026, 9, 8)


class TestResolveTimeframe:
    def test_as_of_resolves_to_single_date(self) -> None:
        outcome = resolve_timeframe("as of 2026-08-31", today=TODAY)
        assert outcome.kind == "resolved"
        assert outcome.as_of_date == date(2026, 8, 31)

    def test_named_last_month_resolves_range(self) -> None:
        outcome = resolve_timeframe("last month", today=TODAY)
        assert outcome.kind == "resolved"
        assert outcome.from_date == date(2026, 8, 1)
        assert outcome.to_date == date(2026, 8, 31)

    def test_named_last_quarter_resolves_range(self) -> None:
        outcome = resolve_timeframe("last quarter", today=TODAY)
        assert outcome.kind == "resolved"
        assert outcome.from_date == date(2026, 4, 1)
        assert outcome.to_date == date(2026, 6, 30)

    def test_relative_days_resolves_range(self) -> None:
        outcome = resolve_timeframe("last 30 days", today=TODAY)
        assert outcome.kind == "resolved"
        assert outcome.from_date == date(2026, 8, 9)
        assert outcome.to_date == TODAY

    def test_iso_range_resolves(self) -> None:
        outcome = resolve_timeframe("2026-08-01 to 2026-08-31", today=TODAY)
        assert outcome.kind == "resolved"
        assert outcome.from_date == date(2026, 8, 1)
        assert outcome.to_date == date(2026, 8, 31)

    def test_unrecognized_phrase_unresolved_with_help(self) -> None:
        outcome = resolve_timeframe("whenever it feels right", today=TODAY)
        assert outcome.kind == "unresolved"
        assert "last month" in outcome.reason  # names the supported options

    def test_empty_timeframe_unresolved(self) -> None:
        outcome = resolve_timeframe(None, today=TODAY)
        assert outcome.kind == "unresolved"


AS_OF_DEF = ReportDefinition(
    slug="ar_aging",
    module="accounting",
    title="AR Aging",
    description=None,
    params=("tenant_id", "as_of_date"),
    dataset="Open Invoices",
    dimensions=("aging bucket",),
    measures=("outstanding balance",),
)

RANGE_DEF = ReportDefinition(
    slug="sales_by_day",
    module="sales",
    title="Sales Orders by Day",
    description=None,
    params=("tenant_id", "from_date", "to_date"),
    dataset="Sales Orders",
    dimensions=("order date", "customer"),
    measures=("order total",),
)

NO_DATE_DEF = ReportDefinition(
    slug="positional",
    module="accounting",
    title="Positional",
    description=None,
    params=("tenant_id",),
    dataset="Ledger",
    dimensions=(),
    measures=(),
)


class TestBuildReportParams:
    def test_as_of_template_with_as_of_intent(self) -> None:
        result = build_report_params(
            definition=AS_OF_DEF,
            timeframe="as of 2026-08-31",
            today=TODAY,
        )
        assert isinstance(result, ParamResolution)
        assert result.params == {"as_of_date": "2026-08-31"}

    def test_as_of_template_with_range_intent_needs_single_date(self) -> None:
        result = build_report_params(
            definition=AS_OF_DEF,
            timeframe="last month",
            today=TODAY,
        )
        assert isinstance(result, TimeframeOutcome)
        assert result.kind == "unresolved"

    def test_range_template_with_range_intent(self) -> None:
        result = build_report_params(
            definition=RANGE_DEF,
            timeframe="last month",
            today=TODAY,
        )
        assert isinstance(result, ParamResolution)
        assert result.params == {"from_date": "2026-08-01", "to_date": "2026-08-31"}

    def test_range_template_with_as_of_intent_needs_range(self) -> None:
        result = build_report_params(
            definition=RANGE_DEF,
            timeframe="as of 2026-08-31",
            today=TODAY,
        )
        assert isinstance(result, TimeframeOutcome)
        assert result.kind == "unresolved"

    def test_no_date_template_ignores_timeframe(self) -> None:
        result = build_report_params(
            definition=NO_DATE_DEF,
            timeframe="last month",
            today=TODAY,
        )
        assert isinstance(result, ParamResolution)
        assert result.params == {}

    def test_no_date_template_without_timeframe_runs(self) -> None:
        """Point-in-time templates need no time period at all.

        Regression: 'Headcount by department' emits ``timeframe: null`` (the
        template declares only tenant_id), yet the resolver demanded a period
        before checking the template's params, so generate returned "Please
        provide a time period." with data:null.
        """
        result = build_report_params(
            definition=NO_DATE_DEF,
            timeframe=None,
            today=TODAY,
        )
        assert isinstance(result, ParamResolution)
        assert result.params == {}

    def test_range_template_without_timeframe_still_clarifies(self) -> None:
        """Range templates still must not run on a missing time period."""
        result = build_report_params(
            definition=RANGE_DEF,
            timeframe=None,
            today=TODAY,
        )
        assert isinstance(result, TimeframeOutcome)
        assert result.kind == "unresolved"

    def test_tenant_id_is_never_set_here(self) -> None:
        # The engine adds tenant_id from the authenticated request; this module
        # must not invent it.
        result = build_report_params(
            definition=RANGE_DEF,
            timeframe="last month",
            today=TODAY,
        )
        assert isinstance(result, ParamResolution)
        assert "tenant_id" not in result.params
