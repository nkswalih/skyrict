"""ABC classification - Pareto analysis by revenue contribution.

Classifies products into A (80% cumulative revenue), B (next 15%),
and C (remaining 5%) bands. Revenue is computed from issue movements
* cost_price over a rolling window.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid


@dataclass(frozen=True, slots=True)
class AbcEntry:
    product_id: uuid.UUID
    revenue: Decimal
    revenue_share: Decimal
    band: str  # "A", "B", or "C"


# Spec thresholds.
_BAND_A_THRESHOLD = Decimal("0.80")  # top 80% of revenue
_BAND_B_THRESHOLD = Decimal("0.95")  # next 15% (80% -> 95%)


def classify_abc(
    products_with_revenue: list[tuple[uuid.UUID, Decimal]],
) -> list[AbcEntry]:
    """Sort by revenue descending, assign A/B/C bands.

    *products_with_revenue* is a list of (product_id, total_revenue) tuples.
    """
    if not products_with_revenue:
        return []

    total = sum(rev for _, rev in products_with_revenue)
    if total <= 0:
        return [
            AbcEntry(product_id=pid, revenue=rev, revenue_share=Decimal(0), band="C")
            for pid, rev in products_with_revenue
        ]

    sorted_items = sorted(products_with_revenue, key=lambda x: x[1], reverse=True)

    entries: list[AbcEntry] = []
    cumulative = Decimal(0)
    for pid, rev in sorted_items:
        share = (rev / total).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        prev_cumulative = cumulative
        cumulative += share
        if prev_cumulative < _BAND_A_THRESHOLD:
            band = "A"
        elif prev_cumulative < _BAND_B_THRESHOLD:
            band = "B"
        else:
            band = "C"
        entries.append(AbcEntry(product_id=pid, revenue=rev, revenue_share=share, band=band))

    return entries
