"""NL query engine - the deterministic pipeline behind /ai/query.

Flow (spec §2.3, hardened):
  1. PARSE   - the LLM maps free text to a :class:`ParsedIntent`. Unusable
     output (invalid JSON/schema) or confidence below the configured
     threshold becomes a low-confidence ABSTENTION - a normal response,
     not an error.
  2. RESOLVE - mentioned product/warehouse names are matched against real
     catalog rows fetched through the gateway; unknown/ambiguous mentions
     produce a CLARIFICATION instead of a guessed query.
  3. EXECUTE - one of three read-only actions against the gateway. No LLM
     output reaches this step unvalidated; no raw SQL exists anywhere.
  4. FORMAT  - deterministic answer templates (no second LLM call: cheaper,
     faster, and unit-testable).

Data residency (spec §5.5): only the user's question text and catalog NAMES
go to the LLM for parsing - never prices or quantities. Parsing runs with
``require_local_only=False`` because product names may travel to cloud
providers; all numbers are computed locally from core data.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.providers import LlmRequest
from ai_agent.features.nl_query.intent import (
    INTENT_SYSTEM_PROMPT,
    IntentAction,
    parse_intent_payload,
)
from ai_agent.features.nl_query.matcher import resolve_product, resolve_warehouse

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable, Sequence

    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.features.nl_query.gateway import (
        InventoryGatewayPort,
        MovementType,
        ProductRef,
        WarehouseRef,
    )
    from ai_agent.features.nl_query.matcher import MatchOutcome

logger = structlog.get_logger("ai_agent.nl_engine")

# Movements have no server-side date filter (verified core gap): the engine
# pages the newest movements via the gateway and filters client-side. This
# window bounds what "recent" means and keeps one query bounded.
_MOVEMENT_LOOKBACK_DAYS = 7
_MAX_ITEMS_SHOWN = 10


@dataclass(frozen=True, slots=True)
class NlQueryResult:
    """Everything /ai/query returns plus what the audit log needs."""

    answer: str
    data: dict[str, object] | None
    model_used: str | None
    latency_ms: int
    parsed_intent: dict[str, object] | None


_ABSTENTION = (
    "I'm not sure I understood the question well enough to answer it. Try "
    "rephrasing it - for example: 'How many laptop chargers do we have in "
    "Bangalore?'"
)


class NlQueryEngine:
    """Parse-resolve-execute-format pipeline over read-only inventory data."""

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]],
        confidence_threshold: float,
    ) -> None:
        self._llm_router = llm_router
        self._gateway_factory = gateway_factory
        self._confidence_threshold = confidence_threshold

    async def ask(self, question: str) -> NlQueryResult:
        """Answer one natural-language inventory question."""
        started = time.perf_counter()

        # --- 1. Parse -----------------------------------------------------
        completion = await self._llm_router.complete(
            LlmRequest(
                system_prompt=INTENT_SYSTEM_PROMPT,
                user_prompt=question.strip(),
                max_tokens=256,
                temperature=0.0,
            )
        )
        try:
            intent = parse_intent_payload(completion.text)
        except ValueError:
            logger.warning("nl_query.unparseable_intent")
            return _finish(answer=_ABSTENTION, model_used=completion.model_used, started=started)
        if intent.confidence < self._confidence_threshold:
            logger.info("nl_query.low_confidence", action=intent.action.value)
            return _finish(
                answer=_ABSTENTION,
                model_used=completion.model_used,
                started=started,
                parsed_intent=intent.to_log_dict(),
            )

        # --- 2. Resolve entities against real catalogs --------------------
        gateway = await self._gateway_factory()
        products = await gateway.list_products()
        warehouses = await gateway.list_warehouses()
        product_match = resolve_product(intent.product_name, products)
        warehouse_match = resolve_warehouse(intent.warehouse_name, warehouses)

        clarification = _clarification_for(product_match, warehouse_match)
        if clarification is not None:
            return _finish(
                answer=clarification,
                model_used=completion.model_used,
                started=started,
                parsed_intent=intent.to_log_dict(),
            )

        # --- 3+4. Execute and format --------------------------------------
        if intent.action is IntentAction.STOCK_COUNT:
            # stock_count is product-scoped in v1; a parse that named no
            # product (e.g. "how many warehouses do we have?") abstains
            # instead of guessing what to count.
            if product_match is None:
                return _finish(
                    answer=("I can look up stock counts per product - which product did you mean?"),
                    model_used=completion.model_used,
                    started=started,
                    parsed_intent=intent.to_log_dict(),
                )
            result = await self._stock_count_result(
                gateway=gateway,
                product=next(p for p in products if p.id == product_match.entity_id),
                warehouse=warehouse_match,
            )
        elif intent.action is IntentAction.BELOW_REORDER:
            result = await self._below_reorder_result(gateway=gateway, products=products)
        elif intent.action is IntentAction.TOTAL_STOCK_VALUE:
            result = await self._total_stock_value_result(
                gateway=gateway,
                products=products,
                warehouse=warehouse_match,
            )
        elif intent.action is IntentAction.HIGHEST_RESERVED:
            result = await self._highest_reserved_result(
                gateway=gateway,
                products=products,
            )
        elif intent.action is IntentAction.LAST_RECEIPT:
            if product_match is None:
                return _finish(
                    answer="I can look up the last receipt for a specific product - which product did you mean?",
                    model_used=completion.model_used,
                    started=started,
                    parsed_intent=intent.to_log_dict(),
                )
            result = await self._last_receipt_result(
                gateway=gateway,
                product=next(p for p in products if p.id == product_match.entity_id),
            )
        elif intent.action is IntentAction.WAREHOUSE_COUNT:
            result = self._warehouse_count_result(warehouses=warehouses)
        else:  # IntentAction.RECENT_MOVEMENTS
            result = await self._recent_movements_result(
                gateway=gateway,
                product_id=product_match.entity_id if product_match else None,
                warehouse_id=warehouse_match.entity_id if warehouse_match else None,
                movement_type=intent.movement_type,
            )
        return _finish(
            answer=result.answer,
            data=result.data,
            model_used=completion.model_used,
            started=started,
            parsed_intent=intent.to_log_dict(),
        )

    async def _stock_count_result(
        self,
        *,
        gateway: InventoryGatewayPort,
        product: ProductRef,
        warehouse: MatchOutcome | None,
    ) -> _ActionOutcome:
        """qty on hand for one product, optionally scoped to one warehouse."""
        warehouse_id = warehouse.entity_id if warehouse else None
        scope = warehouse.display_name if warehouse else "all warehouses"

        levels = await gateway.get_stock_levels(product_id=product.id, warehouse_id=warehouse_id)
        total_on_hand = sum((row.qty_on_hand for row in levels), Decimal(0))
        total_reserved = sum((row.qty_reserved for row in levels), Decimal(0))
        status = "In stock" if total_on_hand > product.reorder_point else "Below reorder point"
        at_note = f" at {scope}" if warehouse else f" across {scope}"
        answer = (
            f"You have {total_on_hand} units of {product.name}{at_note} on hand "
            f"({total_reserved} reserved). "
            f"Reorder point: {product.reorder_point}. Status: {status}."
        )
        return _ActionOutcome(
            answer=answer,
            data={
                "product": product.name,
                "warehouse": scope,
                "qty_on_hand": str(total_on_hand),
                "qty_reserved": str(total_reserved),
                "reorder_point": str(product.reorder_point),
            },
        )

    async def _below_reorder_result(
        self, *, gateway: InventoryGatewayPort, products: Sequence[ProductRef]
    ) -> _ActionOutcome:
        """Aggregate action: every product whose on-hand qty is at/below reorder."""
        levels = await gateway.get_stock_levels()
        by_product: dict[uuid.UUID, Decimal] = {}
        for row in levels:
            by_product[row.product_id] = (
                by_product.get(row.product_id, Decimal(0)) + row.qty_on_hand
            )
        below = sorted(
            (
                (p, qty)
                for p in products
                if (qty := by_product.get(p.id)) is not None and qty <= p.reorder_point
            ),
            key=lambda pair: pair[1],
        )
        if not below:
            return _ActionOutcome(
                answer="Everything is above its reorder point right now.",
                data={"below_reorder": []},
            )
        lines = [
            f"- {p.name} ({p.sku}): {qty} on hand, reorder point {p.reorder_point}"
            for p, qty in below[:_MAX_ITEMS_SHOWN]
        ]
        more = (
            ""
            if len(below) <= _MAX_ITEMS_SHOWN
            else f"\n(and {len(below) - _MAX_ITEMS_SHOWN} more)"
        )
        return _ActionOutcome(
            answer=(
                f"{len(below)} item(s) are below their reorder point:\n" + "\n".join(lines) + more
            ),
            data={"below_reorder": [p.sku for p, _ in below]},
        )

    async def _recent_movements_result(
        self,
        *,
        gateway: InventoryGatewayPort,
        product_id: uuid.UUID | None,
        warehouse_id: uuid.UUID | None,
        movement_type: MovementType | None,
    ) -> _ActionOutcome:
        """Movement history for the resolved filters, newest first."""
        movements = await gateway.list_movements(
            product_id=product_id,
            warehouse_id=warehouse_id,
            movement_type=movement_type,
        )
        cutoff = datetime.now(tz=UTC) - timedelta(days=_MOVEMENT_LOOKBACK_DAYS)
        recent = sorted(
            (m for m in movements if _as_utc(m.created_at) >= cutoff),
            key=lambda m: _as_utc(m.created_at),
            reverse=True,
        )
        if not recent:
            return _ActionOutcome(
                answer="I found no stock movements in the last week for that request.",
                data={"movement_count": 0},
            )
        shown = recent[:_MAX_ITEMS_SHOWN]
        lines = [
            f"- {_as_utc(m.created_at):%Y-%m-%d %H:%M} UTC {m.movement_type}: {m.qty}"
            for m in shown
        ]
        more = (
            "" if len(recent) <= len(shown) else f"\n(showing latest {len(shown)} of {len(recent)})"
        )
        return _ActionOutcome(
            answer="Recent movements:" + more + "\n" + "\n".join(lines),
            data={"movement_count": len(recent)},
        )

    async def _total_stock_value_result(
        self,
        *,
        gateway: InventoryGatewayPort,
        products: Sequence[ProductRef],
        warehouse: MatchOutcome | None,
    ) -> _ActionOutcome:
        """Total monetary value of stock using cost_price (local-only, spec 5.5)."""
        warehouse_id = warehouse.entity_id if warehouse else None
        scope = warehouse.display_name if warehouse else "all warehouses"

        levels = await gateway.get_stock_levels(warehouse_id=warehouse_id)
        cost_by_product: dict[uuid.UUID, Decimal] = {
            p.id: p.cost_price for p in products if p.cost_price is not None
        }
        total_value = Decimal(0)
        items_with_value = 0
        for row in levels:
            cost = cost_by_product.get(row.product_id)
            if cost is not None:
                total_value += row.qty_on_hand * cost
                items_with_value += 1

        answer = (
            f"The total stock value at {scope} is {total_value:.2f} "
            f"(based on cost price for {items_with_value} product(s) with known cost)."
        )
        return _ActionOutcome(
            answer=answer,
            data={"total_value": str(total_value), "scope": scope, "items_count": items_with_value},
        )

    async def _highest_reserved_result(
        self,
        *,
        gateway: InventoryGatewayPort,
        products: Sequence[ProductRef],
    ) -> _ActionOutcome:
        """Product with the highest reserved quantity across all warehouses."""
        levels = await gateway.get_stock_levels()
        reserved_by_product: dict[uuid.UUID, Decimal] = {}
        for row in levels:
            reserved_by_product[row.product_id] = (
                reserved_by_product.get(row.product_id, Decimal(0)) + row.qty_reserved
            )
        if not reserved_by_product or all(v == 0 for v in reserved_by_product.values()):
            return _ActionOutcome(
                answer="No products currently have reserved stock.",
                data={"highest_reserved": None},
            )
        top_id = max(reserved_by_product, key=lambda k: reserved_by_product[k])
        top_qty = reserved_by_product[top_id]
        product = next((p for p in products if p.id == top_id), None)
        name = product.name if product else str(top_id)
        sku = product.sku if product else "N/A"
        return _ActionOutcome(
            answer=(
                f"The product with the highest reserved quantity is {name} ({sku}) "
                f"with {top_qty} units reserved."
            ),
            data={"product_name": name, "sku": sku, "qty_reserved": str(top_qty)},
        )

    async def _last_receipt_result(
        self,
        *,
        gateway: InventoryGatewayPort,
        product: ProductRef,
    ) -> _ActionOutcome:
        """Most recent receipt movement for a given product."""
        movements = await gateway.list_movements(product_id=product.id, movement_type="receipt")
        if not movements:
            return _ActionOutcome(
                answer=f"No receipt movements found for {product.name}.",
                data={"product": product.name, "last_receipt": None},
            )
        latest = max(movements, key=lambda m: _as_utc(m.created_at))
        answer = (
            f"The last receipt for {product.name} was on "
            f"{_as_utc(latest.created_at):%Y-%m-%d %H:%M} UTC "
            f"({latest.qty} units)."
        )
        return _ActionOutcome(
            answer=answer,
            data={
                "product": product.name,
                "last_receipt": _as_utc(latest.created_at).isoformat(),
                "qty": str(latest.qty),
            },
        )

    @staticmethod
    def _warehouse_count_result(
        *,
        warehouses: Sequence[WarehouseRef],
    ) -> _ActionOutcome:
        """Simple count of warehouses."""
        count = len(warehouses)
        names = [w.name for w in warehouses[:_MAX_ITEMS_SHOWN]]
        answer = f"You have {count} warehouse(s)."
        if names:
            answer += " Names: " + ", ".join(names)
            if count > _MAX_ITEMS_SHOWN:
                answer += f" (and {count - _MAX_ITEMS_SHOWN} more)"
        return _ActionOutcome(
            answer=answer,
            data={"warehouse_count": count, "names": names},
        )


@dataclass(frozen=True, slots=True)
class _ActionOutcome:
    answer: str
    data: dict[str, object]


def _as_utc(value: datetime) -> datetime:
    """Normalize to aware UTC so comparisons never mix naive/aware values."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _clarification_for(
    product_match: MatchOutcome | None, warehouse_match: MatchOutcome | None
) -> str | None:
    """Human-readable clarification when a mentioned entity didn't resolve."""
    messages: list[str] = []
    for label, match in (("product", product_match), ("warehouse", warehouse_match)):
        if match is None:
            continue
        if match.status == "unknown":
            messages.append(f"I couldn't find a {label} matching '{match.display_name}'.")
        elif match.status == "ambiguous":
            messages.append(f"Multiple {label}s match '{match.display_name}' - please be specific.")
    if not messages:
        return None
    return " ".join(messages)


def _finish(
    *,
    answer: str,
    model_used: str | None,
    started: float,
    data: dict[str, object] | None = None,
    parsed_intent: dict[str, object] | None = None,
) -> NlQueryResult:
    latency_ms = int((time.perf_counter() - started) * 1000)
    return NlQueryResult(
        answer=answer,
        data=data,
        model_used=model_used,
        latency_ms=latency_ms,
        parsed_intent=parsed_intent,
    )
