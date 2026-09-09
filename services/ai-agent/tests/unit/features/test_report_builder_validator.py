"""Unit tests for the report-builder validator (spec -> catalog whitelist)."""

from __future__ import annotations

from ai_agent.features.report_builder.gateway import ReportDefinition
from ai_agent.features.report_builder.spec import ParsedReportSpec
from ai_agent.features.report_builder.validator import validate_spec

AR_AGING = ReportDefinition(
    slug="ar_aging",
    module="accounting",
    title="AR Aging",
    description=None,
    params=("tenant_id", "as_of_date"),
    dataset="Open Invoices",
    dimensions=("invoice number", "aging bucket", "invoice date"),
    measures=("invoice total", "paid total", "outstanding balance"),
)


def _spec(**overrides: object) -> ParsedReportSpec:
    payload: dict[str, object] = {
        "template_slug": "ar_aging",
        "dataset": "Open Invoices",
        "dimensions": ["aging bucket"],
        "measures": ["outstanding balance"],
        "filters": ["open invoices"],
        "timeframe": "as of 2026-08-31",
        "confidence": 0.95,
    }
    payload.update(overrides)
    return ParsedReportSpec.model_validate(payload)


class TestValidateSpec:
    async def test_ready_for_whitelisted_choice(self) -> None:
        outcome = await validate_spec(
            _spec(),
            definitions=[AR_AGING],
            confidence_threshold=0.75,
        )
        assert outcome.resolution.kind == "ready"
        assert outcome.definition == AR_AGING

    async def test_confidence_below_threshold_abstains(self) -> None:
        outcome = await validate_spec(
            _spec(confidence=0.5),
            definitions=[AR_AGING],
            confidence_threshold=0.75,
        )
        assert outcome.resolution.kind == "abstention"

    async def test_unknown_template_clarifies(self) -> None:
        outcome = await validate_spec(
            _spec(template_slug="totally_made_up"),
            definitions=[AR_AGING],
            confidence_threshold=0.75,
        )
        assert outcome.resolution.kind == "clarification"
        assert "ar_aging" in outcome.resolution.reason  # names the known catalog

    async def test_dataset_mismatch_clarifies(self) -> None:
        outcome = await validate_spec(
            _spec(dataset="Inventory Stock"),
            definitions=[AR_AGING],
            confidence_threshold=0.75,
        )
        assert outcome.resolution.kind == "clarification"

    async def test_missing_dimensions_clarifies(self) -> None:
        outcome = await validate_spec(
            _spec(dimensions=[], measures=[]),
            definitions=[AR_AGING],
            confidence_threshold=0.75,
        )
        assert outcome.resolution.kind == "clarification"

    async def test_off_vocabulary_dimension_clarifies_and_names_it(self) -> None:
        outcome = await validate_spec(
            _spec(dimensions=["supplier name"]),
            definitions=[AR_AGING],
            confidence_threshold=0.75,
        )
        assert outcome.resolution.kind == "clarification"
        assert "supplier name" in outcome.resolution.reason

    async def test_off_vocabulary_measure_clarifies(self) -> None:
        outcome = await validate_spec(
            _spec(measures=["revenue"]),
            definitions=[AR_AGING],
            confidence_threshold=0.75,
        )
        assert outcome.resolution.kind == "clarification"

    async def test_normalized_matching_accepts_case_and_whitespace_variants(self) -> None:
        outcome = await validate_spec(
            _spec(dimensions=["  Aging Bucket  "], measures=["OUTSTANDING balance"]),
            definitions=[AR_AGING],
            confidence_threshold=0.75,
        )
        assert outcome.resolution.kind == "ready"
