"""Inventory Monitor agent - registered via SKY-59 agent_registry.

Provides tools for querying stock and raising restock suggestions,
composing the existing gateway and restock services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from ai_agent.features.nl_query.gateway import InventoryGatewayPort


class InventoryMonitorAgent:
    """Agent that monitors inventory and raises suggestions."""

    def __init__(self, *, gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]]) -> None:
        self._gateway_factory = gateway_factory

    async def query_stock(
        self, *, product_id: uuid.UUID, warehouse_id: uuid.UUID | None = None
    ) -> dict[str, object]:
        gateway = await self._gateway_factory()
        levels = await gateway.get_stock_levels(product_id=product_id, warehouse_id=warehouse_id)
        total_on_hand = sum((row.qty_on_hand for row in levels), 0)
        total_reserved = sum((row.qty_reserved for row in levels), 0)
        return {
            "product_id": str(product_id),
            "qty_on_hand": str(total_on_hand),
            "qty_reserved": str(total_reserved),
        }
