"""ABC classification service - weekly recalc orchestration."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from ai_agent.features.nl_query.gateway import InventoryGatewayPort

logger = structlog.get_logger("ai_agent.abc_service")


class AbcService:
    def __init__(self, *, gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]]) -> None:
        self._gateway_factory = gateway_factory

    async def compute_classification(self) -> list[dict[str, object]]:
        from ai_agent.features.abc.classifier import classify_abc

        gateway = await self._gateway_factory()
        products = await gateway.list_products()
        movements = await gateway.list_movements()

        # Compute revenue per product: sum of issue qty * cost_price.
        cost_map = {p.id: p.cost_price for p in products if p.cost_price is not None}
        revenue_by_product: dict[uuid.UUID, Decimal] = {}
        for m in movements:
            if m.movement_type == "issue" and m.qty < 0:
                cost = cost_map.get(m.product_id)
                if cost is not None:
                    revenue = abs(m.qty) * cost
                    revenue_by_product[m.product_id] = (
                        revenue_by_product.get(m.product_id, Decimal(0)) + revenue
                    )

        items = list(revenue_by_product.items())
        entries = classify_abc(items)

        product_map = {p.id: p for p in products}
        return [
            {
                "product_id": str(e.product_id),
                "product_name": product_map[e.product_id].name
                if e.product_id in product_map
                else str(e.product_id),
                "sku": product_map[e.product_id].sku if e.product_id in product_map else "",
                "revenue": str(e.revenue),
                "revenue_share": str(e.revenue_share),
                "band": e.band,
            }
            for e in entries
        ]

    async def get_summary(self) -> dict[str, int]:
        entries = await self.compute_classification()
        return {
            "A": sum(1 for e in entries if e["band"] == "A"),
            "B": sum(1 for e in entries if e["band"] == "B"),
            "C": sum(1 for e in entries if e["band"] == "C"),
        }
