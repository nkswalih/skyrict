"""Deterministic validation of a parsed report spec against the catalog.

The engine's security boundary (RPT-AI-001, SKY-80): after the LLM parses free
text into a :class:`ParsedReportSpec`, this module re-checks EVERY field the LLM
chose against the REAL catalog fetched through the gateway. It is fail-closed:

- an unknown ``template_slug`` -> clarification ("I don't have that report");
- a ``dataset`` that does not match the template (normalized) -> clarification;
- a ``dimension`` or ``measure`` not in the template's whitelist -> clarification
  naming the offending field (never a partial report);
- a spec with no dimensions or measures -> clarification (nothing to render).

No LLM output reaches the execution step unvalidated: validation is pure and
unit-testable, so a malformed or injection-shaped spec can never become a query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_agent.features.report_builder.gateway import ReportDefinition
    from ai_agent.features.report_builder.spec import ParsedReportSpec


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """Result of validating a spec - either the resolved template or a question."""

    resolution: ValidationResolution
    definition: ReportDefinition | None = None


@dataclass(frozen=True, slots=True)
class ValidationResolution:
    """Classified outcome: ready to run, needs clarification, or abstain.

    ``reason`` is a client-safe human-readable message (never internal detail).
    """

    kind: str  # "ready" | "clarification" | "abstention"
    reason: str = ""


async def validate_spec(
    spec: ParsedReportSpec,
    *,
    definitions: list[ReportDefinition],
    confidence_threshold: float,
) -> ValidationOutcome:
    """Validate a parsed spec against the live catalog.

    Clarity (never a guess): an unknown template, a dataset that does not
    match, or any dimension/measure outside the template's whitelist returns
    a clarification. Confidence below the threshold returns an abstention.
    """
    if spec.confidence < confidence_threshold:
        return ValidationOutcome(
            resolution=ValidationResolution(
                kind="abstention",
                reason=(
                    "I couldn't map that to one of your reports confidently "
                    "enough to run it. Try rephrasing with a specific metric, "
                    "for example: 'AR aging as of last month' or 'sales by "
                    "month for last quarter'."
                ),
            )
        )

    definition = next((d for d in definitions if d.slug == spec.template_slug), None)
    if definition is None:
        known = sorted({d.slug for d in definitions})
        return ValidationOutcome(
            resolution=ValidationResolution(
                kind="clarification",
                reason=(
                    "I don't have a report matching that request. The reports "
                    "I can build are: " + ", ".join(known) + "."
                ),
            )
        )

    if definition.dataset and _normalize(spec.dataset) != _normalize(definition.dataset):
        return ValidationOutcome(
            resolution=ValidationResolution(
                kind="clarification",
                reason=(
                    f"The dataset '{spec.dataset}' doesn't match the "
                    f"{definition.title} report. Try one of: {definition.dataset}."
                ),
            )
        )

    if not spec.dimensions or not spec.measures:
        return ValidationOutcome(
            resolution=ValidationResolution(
                kind="clarification",
                reason=(
                    "Which breakdown and metric would you like? For example: "
                    "'group the aging report by aging bucket and show the "
                    "outstanding balance'."
                ),
            )
        )

    unknown_dims = [
        d for d in spec.dimensions if _normalize(d) not in _norm_set(definition.dimensions)
    ]
    unknown_measures = [
        m for m in spec.measures if _normalize(m) not in _norm_set(definition.measures)
    ]
    unknown = unknown_dims + unknown_measures
    if unknown:
        return ValidationOutcome(
            resolution=ValidationResolution(
                kind="clarification",
                reason=(
                    f"I can't break '{definition.title}' down by {unknown[0]!r}. "
                    "Available: dimensions ["
                    + ", ".join(definition.dimensions)
                    + "] and measures ["
                    + ", ".join(definition.measures)
                    + "]."
                ),
            )
        )

    return ValidationOutcome(
        resolution=ValidationResolution(kind="ready"),
        definition=definition,
    )


def _norm_set(values: tuple[str, ...]) -> set[str]:
    return {_normalize(v) for v in values}


def _normalize(value: str) -> str:
    """Lowercase, strip, and collapse whitespace for tolerant matching."""
    return " ".join(value.strip().lower().split())
