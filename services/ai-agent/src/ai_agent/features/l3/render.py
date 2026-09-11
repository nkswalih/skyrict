"""Token substitution - replace {{TOKEN}} placeholders with verified figures."""

from __future__ import annotations

from ai_agent.features.l3.narrate import L3NarrativeText


def render_narrative(text: L3NarrativeText, figures: dict[str, str]) -> L3NarrativeText:
    """Replace ``{{TOKEN}}`` occurrences in title, summary, points, caveat."""
    return L3NarrativeText(
        title=_sub(text.title, figures),
        summary=_sub(text.summary, figures),
        points=[_sub(p, figures) for p in text.points],
        caveat=_sub(text.caveat, figures),
        model_used=text.model_used,
        latency_ms=text.latency_ms,
    )


def _sub(text: str, figures: dict[str, str]) -> str:
    result = text
    for token, value in figures.items():
        result = result.replace(token, value)
    return result
