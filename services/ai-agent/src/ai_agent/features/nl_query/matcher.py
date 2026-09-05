"""Entity resolution - match user-mentioned names to real catalog rows.

Spec §2.4: "Parsed intent validated against actual product/warehouse names
before execution". A mention that matches nothing or ambiguously produces a
clarification response, never a guessed query. Matching is deterministic and
predictable, in descending strictness:

1. case-insensitive exact name
2. containment — the whole catalog name appears inside the mention
   ("laptop chargers" contains "char"->"Charger")
3. token overlap — a shared significant word between mention and name
   ("mobile phones" shares "mobile" with "Mobile")
4. fuzzy near-miss spelling ("chargers" ≈ "Charger")

Product/warehouse names are DATA (spec §5.6): they are echoed back verbatim,
never interpreted.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from ai_agent.features.nl_query.gateway import ProductRef, WarehouseRef


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    """Result of resolving one mentioned name against a catalog."""

    entity_id: uuid.UUID | None
    status: str  # "matched" | "unknown" | "ambiguous"
    # The canonical catalog name when matched; the raw user text otherwise.
    display_name: str


def _match_name(mentioned: str, candidates: Sequence[tuple[uuid.UUID, str]]) -> MatchOutcome:
    lowered = mentioned.strip().lower()
    if not lowered:
        return MatchOutcome(None, "unknown", mentioned)

    exact = [(eid, name) for eid, name in candidates if name.lower() == lowered]
    if len(exact) == 1:
        return MatchOutcome(exact[0][0], "matched", exact[0][1])

    # Containment — the whole catalog name inside the mention. "laptop
    # chargers" contains catalog name "Charger" even though the phrase is not
    # a substring of the name.
    containing = [(eid, name) for eid, name in candidates if name.lower() in lowered]
    if len(containing) == 1:
        return MatchOutcome(containing[0][0], "matched", containing[0][1])
    if len(containing) > 1:
        return MatchOutcome(None, "ambiguous", mentioned)

    # Token overlap — one shared significant word resolves related phrasings
    # like "mobile phones" against a product named "Mobile".
    mention_tokens = _significant_tokens(lowered)
    overlapping = [
        (eid, name)
        for eid, name in candidates
        if mention_tokens & _significant_tokens(name.lower())
    ]
    if len(overlapping) == 1:
        return MatchOutcome(overlapping[0][0], "matched", overlapping[0][1])
    if len(overlapping) > 1:
        return MatchOutcome(None, "ambiguous", mentioned)

    # Fuzzy — near-miss spelling/singular-plural ("chargers" ≈ "Charger").
    fuzzy = [
        (eid, name)
        for eid, name in candidates
        if SequenceMatcher(None, name.lower(), lowered).ratio() >= _FUZZY_RATIO
    ]
    if len(fuzzy) == 1:
        return MatchOutcome(fuzzy[0][0], "matched", fuzzy[0][1])
    if len(fuzzy) > 1:
        return MatchOutcome(None, "ambiguous", mentioned)
    return MatchOutcome(None, "unknown", mentioned)


_FUZZY_RATIO = 0.62


def _significant_tokens(text: str) -> set[str]:
    """Words long enough to carry meaning (helps matching avoid false hits)."""
    return {token for token in text.split() if len(token) > 2}


def resolve_product(mentioned: str | None, products: Sequence[ProductRef]) -> MatchOutcome | None:
    """Resolve a product mention; ``None`` when the question named no product."""
    if mentioned is None:
        return None
    return _match_name(mentioned, [(p.id, p.name) for p in products])


def resolve_warehouse(
    mentioned: str | None, warehouses: Sequence[WarehouseRef]
) -> MatchOutcome | None:
    """Resolve a warehouse mention; ``None`` when none was named."""
    if mentioned is None:
        return None
    return _match_name(mentioned, [(w.id, w.name) for w in warehouses])
