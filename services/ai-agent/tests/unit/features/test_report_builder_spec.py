"""Unit tests for the report-builder spec: schema, parsing, system prompt."""

from __future__ import annotations

from ai_agent.features.report_builder.spec import (
    ParsedReportSpec,
    parse_report_spec_payload,
    report_spec_system_prompt,
)


class TestParsedReportSpec:
    def test_accepts_full_valid_payload(self) -> None:
        spec = ParsedReportSpec.model_validate(
            {
                "template_slug": "ar_aging",
                "dataset": "Open Invoices",
                "dimensions": ["aging bucket"],
                "measures": ["outstanding balance"],
                "filters": ["open invoices"],
                "timeframe": "as of 2026-08-31",
                "confidence": 0.95,
            }
        )
        assert spec.template_slug == "ar_aging"
        assert spec.confidence == 0.95

    def test_rejects_missing_required_fields(self) -> None:
        import pydantic
        import pytest

        with pytest.raises(pydantic.ValidationError):
            ParsedReportSpec.model_validate({"confidence": 0.9})

    def test_rejects_out_of_range_confidence(self) -> None:
        import pydantic
        import pytest

        with pytest.raises(pydantic.ValidationError):
            ParsedReportSpec.model_validate(
                {
                    "template_slug": "ar_aging",
                    "dataset": "Open Invoices",
                    "confidence": 1.5,
                }
            )

    def test_to_log_dict_is_json_safe(self) -> None:
        spec = ParsedReportSpec(
            template_slug="ar_aging",
            dataset="Open Invoices",
            dimensions=["aging bucket"],
            measures=["outstanding balance"],
            filters=["open invoices"],
            timeframe="as of 2026-08-31",
            confidence=0.95,
        )
        payload = spec.to_log_dict()
        assert payload["template_slug"] == "ar_aging"
        assert payload["confidence"] == 0.95


class TestParseReportSpecPayload:
    def test_parses_valid_json(self) -> None:
        raw = (
            '{"template_slug": "ar_aging", "dataset": "Open Invoices", '
            '"dimensions": ["aging bucket"], "measures": ["outstanding balance"], '
            '"filters": [], "timeframe": null, "confidence": 0.9}'
        )
        spec = parse_report_spec_payload(raw)
        assert spec.template_slug == "ar_aging"

    def test_rejects_invalid_json(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            parse_report_spec_payload("not json at all")

    def test_rejects_schema_failure(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            parse_report_spec_payload('{"template_slug": "ar_aging"}')


class TestReportSpecSystemPrompt:
    class _Item:
        def __init__(
            self,
            slug: str,
            title: str,
            dataset: str | None,
            dimensions: tuple[str, ...],
            measures: tuple[str, ...],
        ) -> None:
            self.slug = slug
            self.title = title
            self.dataset = dataset
            self.dimensions = dimensions
            self.measures = measures

    def test_prompt_embeds_catalog_whitelist(self) -> None:
        catalog = [
            self._Item(
                slug="ar_aging",
                title="AR Aging",
                dataset="Open Invoices",
                dimensions=("aging bucket",),
                measures=("outstanding balance",),
            )
        ]
        prompt = report_spec_system_prompt(catalog)
        assert "ar_aging" in prompt
        assert "Open Invoices" in prompt
        assert "aging bucket" in prompt
        assert "outstanding balance" in prompt

    def test_prompt_instructs_the_model_to_never_emit_sql(self) -> None:
        # The anti-SQL rule is part of the prompt contract: the model must not
        # emit SQL/table names/param values - only human words + the schema.
        prompt = report_spec_system_prompt([])
        assert "NEVER emit SQL" in prompt
        assert "parameter values" in prompt

    def test_prompt_with_empty_catalog_degrades_gracefully(self) -> None:
        prompt = report_spec_system_prompt([])
        assert "(no catalog available)" in prompt
