"""Report builder engine - the deterministic pipeline behind /ai/report-builder.

Flow (RPT-AI-001, SKY-80), hardened exactly like the NL query engine:
  1. PARSE   - the LLM maps free text to a :class:`ParsedReportSpec`. Unusable
     output (invalid JSON/schema) or confidence below the threshold becomes an
     ABSTENTION - a normal response, not an error.
  2. VALIDATE - every field the LLM chose is re-checked against the REAL catalog
     fetched through the gateway. Unknown template / off-vocabulary dimension or
     measure / unmatched dataset -> CLARIFICATION (never a guessed report). This
     step is the security boundary: no LLM output reaches execution unvalidated.
  3. RESOLVE - the human-readable timeframe is turned into the template's
     declared bind params (dates). Unrecognized timeframe -> clarification.
  4. EXECUTE - run the report through the gateway (caller's scoped identity,
     read-only Core path). No raw SQL exists anywhere; the SLUG names a
     canonical template.
  5. RESULT - structured columns/rows + the resolved params + a chart hint
     derived deterministically from the chosen dimensions (client renders).

Data sent to the LLM: the user's prompt and the catalog's names/measures only -
never row data or values (residency-safe; no local-only clearance needed).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.exceptions import ValidationError
from ai_agent.core.providers import LlmRequest
from ai_agent.features.report_builder.params import ParamResolution, build_report_params
from ai_agent.features.report_builder.spec import (
    ParsedReportSpec,
    parse_report_spec_payload,
    report_spec_system_prompt,
)
from ai_agent.features.report_builder.validator import (
    validate_spec,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.features.report_builder.gateway import (
        CreatedReport,
        ReportDefinition,
        ReportGatewayPort,
        ReportRun,
    )

logger = structlog.get_logger("ai_agent.report_builder_engine")


@dataclass(frozen=True, slots=True)
class ReportBuilderResult:
    """Everything /ai/report-builder/generate returns plus audit needs."""

    answer: str
    data: dict[str, object] | None
    model_used: str | None
    latency_ms: int
    parsed_spec: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class _GeneratedData:
    """Structured payload for a successful generated report."""

    definition: ReportDefinition
    run: ReportRun
    params: dict[str, object]
    chart_hint: str | None


_ABSTENTION = (
    "I couldn't turn that into a report. Try describing a specific metric and "
    "period, for example: 'AR aging as of last month' or 'sales orders by day "
    "for last quarter'."
)


class ReportBuilderEngine:
    """Parse-validate-resolve-execute pipeline over Core's report catalog."""

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        gateway_factory: Callable[[], Awaitable[ReportGatewayPort]],
        confidence_threshold: float,
    ) -> None:
        self._llm_router = llm_router
        self._gateway_factory = gateway_factory
        self._confidence_threshold = confidence_threshold

    async def generate(
        self, prompt: str, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReportBuilderResult:
        """Build and run one natural-language report request."""
        started = time.perf_counter()

        # --- 1. Fetch the live catalog (the prompt's whitelist) ------------
        gateway = await self._gateway_factory()
        definitions = await gateway.list_definitions()

        # --- 2. Parse ------------------------------------------------------
        completion = await self._llm_router.complete(
            LlmRequest(
                system_prompt=report_spec_system_prompt(definitions),
                user_prompt=prompt.strip(),
                think=False,
                json_mode=True,
                max_tokens=512,
                temperature=0.0,
            )
        )
        spec = _parse_or_none(completion.text)
        if spec is None or spec.confidence < self._confidence_threshold:
            return _finish(
                answer=_ABSTENTION,
                model_used=completion.model_used,
                started=started,
                parsed_spec=spec.to_log_dict() if spec is not None else None,
            )

        # --- 3. Validate against the real catalog --------------------------
        outcome = await validate_spec(
            spec,
            definitions=definitions,
            confidence_threshold=self._confidence_threshold,
        )
        resolution = outcome.resolution
        if resolution.kind != "ready" or outcome.definition is None:
            return _finish(
                answer=resolution.reason,
                model_used=completion.model_used,
                started=started,
                parsed_spec=spec.to_log_dict(),
            )
        definition = outcome.definition

        # --- 4. Resolve params from the timeframe intent -------------------
        param_outcome = build_report_params(
            definition=definition,
            timeframe=spec.timeframe,
        )
        if isinstance(param_outcome, ParamResolution):
            params: dict[str, object] = dict(param_outcome.params)
        else:
            # unresolved timeframe -> clarification
            return _finish(
                answer=param_outcome.reason,
                model_used=completion.model_used,
                started=started,
                parsed_spec=spec.to_log_dict(),
            )
        params["tenant_id"] = str(tenant_id)

        # --- 5. Execute through the gateway (read-only Core path) ----------
        run = await gateway.run_report(definition.slug, params)

        generated = _GeneratedData(
            definition=definition,
            run=run,
            params=params,
            chart_hint=_chart_hint(spec),
        )
        return _finish(
            answer=_answer_for(run, definition),
            data={
                "slug": definition.slug,
                "title": definition.title,
                "module": definition.module,
                "columns": run.columns,
                "rows": run.rows,
                "truncated": run.truncated,
                "chart_hint": generated.chart_hint,
                "params": generated.params,
                "parsed_spec": spec.to_log_dict(),
            },
            model_used=completion.model_used,
            started=started,
            parsed_spec=spec.to_log_dict(),
        )

    async def save(
        self,
        *,
        template_slug: str,
        title: str,
        description: str | None,
        slug: str,
        params: dict[str, object],
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CreatedReport:
        """Persist a resolved report as a new runnable definition via Core.

        Core enforces the invariant that stored SQL is byte-for-byte a
        whitelisted template (it resolves template SQL from ``source_slug``
        server-side). This method only supplies the metadata, the chosen
        template's slug, and the template's declared params - never any SQL.

        Defense-in-depth:
        1. Re-fetch the catalog and resolve ``template_slug`` to a real
           definition - unknown template is a 422, never a guessed save.
        2. Only the template's declared params may travel as ``default_params``
           (values are pre-fill only; Core does not persist them).
        3. ``module``/``params`` come from the catalog definition - client
           metadata never overrides the template.
        """
        gateway = await self._gateway_factory()
        definitions = await gateway.list_definitions()
        definition = next((d for d in definitions if d.slug == template_slug), None)
        if definition is None:
            raise ValidationError(f"Report template {template_slug!r} is not whitelisted")

        unknown = set(params) - set(definition.params) - {"tenant_id"}
        if unknown:
            raise ValidationError(f"Unknown report parameters: {', '.join(sorted(unknown))}")

        return await gateway.create_definition(
            slug=slug,
            title=title,
            module=definition.module,
            description=description,
            source_slug=template_slug,
            params=list(definition.params),
            default_params=params,
        )


def _chart_hint(spec: ParsedReportSpec) -> str | None:
    """Deterministic chart selection from the CHOSEN dimensions (client renders).

    Matches the web client's planChart() heuristic on the dimensions the user
    actually asked to break by: a time dimension suggests a line; a single
    low-cardinality dimension suggests a bar; otherwise the client falls back
    to a table. The engine returns a hint; the UI owns the actual charting.
    """
    lowered = [d.lower() for d in spec.dimensions]
    if any("date" in d or "period" in d for d in lowered):
        return "line"
    if len(spec.dimensions) == 1:
        return "bar"
    return None


def _answer_for(run: ReportRun, definition: ReportDefinition) -> str:
    rows = len(run.rows)
    truncated = " (truncated)" if run.truncated else ""
    return f"Here is the {definition.title} report{truncated}: {rows} result row(s)."


def _parse_or_none(raw: str) -> ParsedReportSpec | None:
    """Strict spec parse with a tolerant extraction fallback (mirrors NL engine)."""
    try:
        return parse_report_spec_payload(raw)
    except ValueError:
        extracted = _extract_json_object(raw)
        if extracted is None:
            logger.warning("report_builder.unparseable_spec")
            return None
    try:
        return parse_report_spec_payload(extracted)
    except ValueError:
        logger.warning("report_builder.unparseable_spec")
        return None


def _extract_json_object(raw: str) -> str | None:
    """Return the first balanced ``{...}`` in ``raw``, or ``None``."""
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(raw)):
        if raw[index] == "{":
            depth += 1
        elif raw[index] == "}":
            depth -= 1
            if depth == 0:
                return raw[start : index + 1]
    return None


def _finish(
    *,
    answer: str,
    model_used: str | None,
    started: float,
    data: dict[str, object] | None = None,
    parsed_spec: dict[str, object] | None = None,
) -> ReportBuilderResult:
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ReportBuilderResult(
        answer=answer,
        data=data,
        model_used=model_used,
        latency_ms=latency_ms,
        parsed_spec=parsed_spec,
    )
