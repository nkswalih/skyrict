"""Unit tests for the report-builder engine pipeline (SKY-80).

The engine is exercised with a scripted LLM router double and an in-memory
report gateway double - the full parse-validate-resolve-execute behavior
matrix without any network or database.
"""

from __future__ import annotations

import json
import uuid

import pytest

from ai_agent.core.exceptions import ValidationError
from ai_agent.core.providers.base import LlmCompletion, LlmRequest
from ai_agent.features.report_builder.engine import ReportBuilderEngine
from ai_agent.features.report_builder.gateway import (
    CreatedReport,
    ReportDefinition,
    ReportRun,
)

TENANT_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")

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

SALES_BY_DAY = ReportDefinition(
    slug="sales_by_day",
    module="sales",
    title="Sales Orders by Day",
    description=None,
    params=("tenant_id", "from_date", "to_date"),
    dataset="Sales Orders",
    dimensions=("order date", "customer"),
    measures=("order total",),
)

AR_RUN = ReportRun(
    columns=["invoice number", "aging bucket", "outstanding balance"],
    rows=[
        {
            "invoice number": "INV-0001",
            "aging bucket": "0-30",
            "outstanding balance": "1250.0000",
        }
    ],
    truncated=False,
)


class FakeLlmRouter:
    """Returns one scripted completion; records requests for assertions."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[LlmRequest] = []

    async def complete(self, request: LlmRequest) -> LlmCompletion:
        self.requests.append(request)
        return LlmCompletion(text=self.text, model_used="fake-model", latency_ms=1)


class FakeReportGateway:
    """In-memory ReportGatewayPort."""

    def __init__(self, definitions: list[ReportDefinition] | None = None) -> None:
        self.definitions = definitions or [AR_AGING, SALES_BY_DAY]
        self.calls: list[str] = []
        self.run_params: list[dict[str, object]] = []
        self.created: list[dict[str, object]] = []

    async def list_definitions(self) -> list[ReportDefinition]:
        self.calls.append("list_definitions")
        return self.definitions

    async def run_report(self, slug: str, params: dict[str, object]) -> ReportRun:
        self.calls.append(f"run:{slug}")
        self.run_params.append(params)
        return AR_RUN

    async def create_definition(
        self,
        *,
        slug: str,
        title: str,
        module: str,
        description: str | None,
        source_slug: str,
        params: list[str],
        default_params: dict[str, object] | None = None,
    ) -> CreatedReport:
        self.calls.append("create_definition")
        self.created.append(
            {
                "slug": slug,
                "title": title,
                "module": module,
                "description": description,
                "source_slug": source_slug,
                "params": params,
                "default_params": default_params or {},
            }
        )
        return CreatedReport(
            definition=AR_AGING,
            default_params=default_params or {},
        )


def _spec_payload(**overrides: object) -> str:
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
    return json.dumps(payload)


def _make_engine(
    llm_text: str,
    definitions: list[ReportDefinition] | None = None,
) -> tuple[ReportBuilderEngine, FakeLlmRouter, FakeReportGateway]:
    router = FakeLlmRouter(llm_text)
    gateway = FakeReportGateway(definitions)

    async def factory() -> FakeReportGateway:
        return gateway

    engine = ReportBuilderEngine(
        llm_router=router,  # type: ignore[arg-type]
        gateway_factory=factory,
        confidence_threshold=0.75,
    )
    return engine, router, gateway


class TestGenerate:
    async def test_happy_path_runs_report_and_returns_structured_data(self) -> None:
        engine, router, gateway = _make_engine(_spec_payload())

        result = await engine.generate(
            "AR aging as of last month",
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert result.data is not None
        assert result.data["slug"] == "ar_aging"
        assert result.data["columns"] == AR_RUN.columns
        assert result.data["rows"] == AR_RUN.rows
        assert result.data["chart_hint"] == "bar"  # single dim, no time axis
        assert result.data["params"] == {
            "as_of_date": "2026-08-31",
            "tenant_id": str(TENANT_ID),
        }
        assert result.model_used == "fake-model"
        assert gateway.calls == ["list_definitions", "run:ar_aging"]
        assert router.requests[0].system_prompt != ""

    async def test_happy_path_time_dimension_hints_line(self) -> None:
        engine, _, _ = _make_engine(
            _spec_payload(dimensions=["invoice date"]),
        )

        result = await engine.generate(
            "AR aging grouped by invoice date",
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert result.data is not None
        assert result.data["chart_hint"] == "line"

    async def test_low_confidence_abstains_without_running(self) -> None:
        engine, _, gateway = _make_engine(_spec_payload(confidence=0.4))

        result = await engine.generate(
            "AR aging",
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert result.data is None
        assert "couldn't" in result.answer.lower()
        assert "run:" not in " ".join(gateway.calls)

    async def test_unparseable_output_abstains(self) -> None:
        engine, _, gateway = _make_engine("I am a helpful assistant")

        result = await engine.generate(
            "AR aging",
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert result.data is None
        assert "couldn't" in result.answer.lower()
        assert gateway.calls == ["list_definitions"]

    async def test_unknown_template_clarifies(self) -> None:
        engine, _, gateway = _make_engine(
            _spec_payload(template_slug="made_up_report"),
        )

        result = await engine.generate(
            "the made up report",
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert result.data is None
        assert "ar_aging" in result.answer  # names the known catalog
        assert gateway.calls == ["list_definitions"]

    async def test_off_vocabulary_measure_clarifies(self) -> None:
        engine, _, gateway = _make_engine(_spec_payload(measures=["revenue"]))

        result = await engine.generate(
            "AR aging with revenue",
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert result.data is None
        assert "revenue" in result.answer
        assert gateway.calls == ["list_definitions"]

    async def test_unresolved_timeframe_clarifies(self) -> None:
        engine, _, gateway = _make_engine(_spec_payload(timeframe="this fiscal era"))

        result = await engine.generate(
            "AR aging this fiscal era",
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert result.data is None
        assert "time period" in result.answer.lower() or "understand" in result.answer.lower()
        assert gateway.calls == ["list_definitions"]


class TestSave:
    async def test_save_creates_definition_from_template(self) -> None:
        engine, _, gateway = _make_engine(_spec_payload())

        created = await engine.save(
            template_slug="ar_aging",
            title="My Monthly Aging",
            description="Saved from the AI builder",
            slug="my_monthly_aging",
            params={"as_of_date": "2026-08-31", "tenant_id": str(TENANT_ID)},
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert created.definition.slug == "ar_aging"
        assert gateway.calls == ["list_definitions", "create_definition"]
        payload = gateway.created[0]
        assert payload["slug"] == "my_monthly_aging"
        assert payload["source_slug"] == "ar_aging"
        assert payload["module"] == "accounting"  # derived from template, not client
        assert payload["params"] == ["tenant_id", "as_of_date"]
        assert payload["default_params"] == {
            "as_of_date": "2026-08-31",
            "tenant_id": str(TENANT_ID),
        }

    async def test_save_unknown_template_rejected(self) -> None:
        engine, _, gateway = _make_engine(_spec_payload())

        with pytest.raises(ValidationError):
            await engine.save(
                template_slug="not_a_template",
                title="X",
                description=None,
                slug="x",
                params={},
                tenant_id=TENANT_ID,
                user_id=USER_ID,
            )
        assert gateway.calls == ["list_definitions"]

    async def test_save_undeclared_param_rejected(self) -> None:
        engine, _, gateway = _make_engine(_spec_payload())

        with pytest.raises(ValidationError):
            await engine.save(
                template_slug="ar_aging",
                title="X",
                description=None,
                slug="x",
                params={"bogus_param": "1"},
                tenant_id=TENANT_ID,
                user_id=USER_ID,
            )
        assert gateway.calls == ["list_definitions"]
