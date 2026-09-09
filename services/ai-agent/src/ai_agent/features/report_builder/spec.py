"""Structured report-builder spec (RPT-AI-001, SKY-80).

The LLM's ONLY job in the report-builder path is to map free text onto this
schema and pick ONE canonical template by slug. Everything downstream is
deterministic code - no LLM output is ever executed directly, and the LLM
never emits SQL, table names, or parameters:

- ``template_slug`` must name a whitelisted catalog entry (validated against
  the real catalog fetched through the gateway).
- ``dataset``, ``dimensions``, ``measures`` must all appear in that template's
  declared vocabulary (validated server-side in the engine).
- ``filters`` / ``timeframe`` are the human-readable intent the engine turns
  into the template's declared bind parameters (dates); the LLM never picks a
  parameter name or value that the template does not declare.

A payload that fails schema validation, names an unknown template, or picks a
dimension/measure outside the template's whitelist becomes a clarification or
abstention - never a partial or guessed report.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ParsedReportSpec(BaseModel):
    """Validated parse of one natural-language report request."""

    model_config = ConfigDict(frozen=True)

    # The canonical whitelisted template this request maps to (by catalog slug).
    template_slug: str = Field(min_length=1, max_length=64)
    # Free-text description of the dataset the user wants (mirrors the
    # template's ``dataset``; validated against it).
    dataset: str = Field(min_length=1, max_length=120)
    # Selectable grouping dimensions the user asked to break out by
    # (each must exist in the template's whitelist).
    dimensions: list[str] = Field(default_factory=list, max_length=160)
    # Selectable numeric measures the user wants (each must exist in the
    # template's whitelist).
    measures: list[str] = Field(default_factory=list, max_length=160)
    # Human-readable filter intent, e.g. "open invoices", "non-terminated".
    filters: list[str] = Field(default_factory=list, max_length=400)
    # Human-readable time window intent, e.g. "last quarter", "as of Aug 31".
    timeframe: str | None = Field(default=None, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)

    def to_log_dict(self) -> dict[str, object]:
        """JSON-safe projection for ai_query_log.parsed_intent."""
        return {
            "template_slug": self.template_slug,
            "dataset": self.dataset,
            "dimensions": self.dimensions,
            "measures": self.measures,
            "filters": self.filters,
            "timeframe": self.timeframe,
            "confidence": self.confidence,
        }


def parse_report_spec_payload(raw: str) -> ParsedReportSpec:
    """Parse the LLM's raw completion text into a validated report spec.

    Raises:
        ValueError: When the text is not JSON or fails schema validation -
            callers treat this as an unusable parse (clarification/abstention).
    """
    try:
        data = json.loads(raw)
        return ParsedReportSpec.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("LLM output did not match the report spec schema") from exc


def report_spec_system_prompt(catalog: object) -> str:
    """Build the LLM system prompt from the live report catalog.

    The catalog names the EXACT set of templates, dimensions, and measures the
    LLM may choose from. It is injected fresh per request so the model never
    guesses a slug, dataset, dimension, or measure that does not exist - the
    prompt is a whitelist, and the server re-validates everything it returns.
    """
    header = (
        "You translate a natural-language report request into strict JSON that "
        "maps onto ONE of the catalog reports below. Respond with ONLY a JSON "
        "object, no prose, matching exactly:\n"
        "{\n"
        '  "template_slug": "<a catalog slug>",\n'
        '  "dataset": "<short dataset description>",\n'
        '  "dimensions": ["<dimension 1>", ...],\n'
        '  "measures": ["<measure 1>", ...],\n'
        '  "filters": ["<human-readable filter>", ...],\n'
        '  "timeframe": "<human-readable time window, or null>",\n'
        '  "confidence": <0.0-1.0>\n'
        "}\n\n"
        "RULES:\n"
        "- Choose the single catalog template (by slug) that best fits the request.\n"
        "- ONLY use dimensions and measures that exist on that template. If the "
        "request asks for a dimension/measure the template does not provide, use "
        "confidence below 0.5 and still return the closest template.\n"
        "- Only choose a template whose dataset matches the request. Unknown "
        "requests (no template fits) use confidence below 0.5 and the closest "
        "template.\n"
        "- You NEVER emit SQL, table names, or parameter values. filters/timeframe "
        "are human words only.\n\n"
        "CATALOG (the only valid templates):\n"
    )
    lines: list[str] = []
    catalog_items = catalog if isinstance(catalog, list) else []
    for item in catalog_items:
        slug = getattr(item, "slug", None)
        title = getattr(item, "title", None)
        dataset = getattr(item, "dataset", None)
        dims = ", ".join(getattr(item, "dimensions", ())) or "(none)"
        measures = ", ".join(getattr(item, "measures", ())) or "(none)"
        if slug is None:
            continue
        lines.append(
            f"- slug={slug!r}; title={title!r}; dataset={dataset!r} "
            f"; dimensions=[{dims}] ; measures=[{measures}]"
        )
    if not lines:
        return header + "(no catalog available)"
    return header + "\n".join(lines)
