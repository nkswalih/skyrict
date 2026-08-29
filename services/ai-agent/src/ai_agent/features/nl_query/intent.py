"""Structured NL-query intent (spec §2.3 step 2).

The LLM's ONLY job in the query path is to map free text onto this schema.
Everything downstream is deterministic code - no LLM output is ever executed
directly (prompt-injection defense, spec §5.6): a payload that fails this
model's validation becomes a low-confidence abstention, never a query.

The action set is deliberately SMALL: only intents the inventory gateway can
execute deterministically today. Expanding it is a conscious product decision,
not an accident of prompt wording.
"""

from __future__ import annotations

import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# NOTE: runtime import on purpose - pydantic resolves this annotation while
# building the model schema, so a TYPE_CHECKING-only import breaks at boot.
from ai_agent.features.nl_query.gateway import MovementType  # noqa: TC001


class IntentAction(StrEnum):
    """Executable read-only actions (spec 2.2 examples, v1 subset)."""

    STOCK_COUNT = "stock_count"  # qty on hand for product [+ warehouse]
    BELOW_REORDER = "below_reorder"  # what is below reorder point
    RECENT_MOVEMENTS = "recent_movements"  # movements for product/warehouse/type
    TOTAL_STOCK_VALUE = "total_stock_value"  # sum of qty_on_hand * cost_price
    HIGHEST_RESERVED = "highest_reserved"  # product with highest qty_reserved
    LAST_RECEIPT = "last_receipt"  # most recent receipt for a product
    WAREHOUSE_COUNT = "warehouse_count"  # how many warehouses


class ParsedIntent(BaseModel):
    """Validated parse of one user question."""

    model_config = ConfigDict(frozen=True)

    action: IntentAction
    # Entity names as MENTIONED by the user - resolved against real catalog
    # rows before execution; never used as-is in any query.
    product_name: str | None = Field(default=None, max_length=200)
    warehouse_name: str | None = Field(default=None, max_length=200)
    movement_type: MovementType | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    def to_log_dict(self) -> dict[str, object]:
        """JSON-safe projection for ai_query_log.parsed_intent."""
        return {
            "action": self.action.value,
            "product_name": self.product_name,
            "warehouse_name": self.warehouse_name,
            "movement_type": self.movement_type,
            "confidence": self.confidence,
        }


def parse_intent_payload(raw: str) -> ParsedIntent:
    """Parse the LLM's raw completion text into a validated intent.

    Raises:
        ValueError: When the text is not JSON or fails schema validation -
            callers treat both identically as an unusable parse.
    """
    try:
        data = json.loads(raw)
        return ParsedIntent.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("LLM output did not match the intent schema") from exc


INTENT_SYSTEM_PROMPT = """You translate inventory questions into strict JSON.

Respond with ONLY a JSON object, no prose, matching exactly:
{
  "action": "<stock_count|below_reorder|recent_movements|total_stock_value|highest_reserved|last_receipt|warehouse_count>",
  "product_name": "<product name mentioned, or null>",
  "warehouse_name": "<warehouse name mentioned, or null>",
  "movement_type": "<receipt|issue|transfer|adjustment|reservation|release, or null>",
  "confidence": <0.0-1.0>
}

Rules:
- stock_count: how many units of a product exist (optionally at one warehouse).
- below_reorder: which items are below their reorder point / need reordering.
- recent_movements: stock movement history (receipts, issues, transfers...).
- total_stock_value: total monetary value of stock (optionally at one warehouse).
- highest_reserved: which product has the highest reserved quantity.
- last_receipt: when was the last receipt/shipment for a product.
- warehouse_count: how many warehouses exist.
- If the question matches none of these actions, use confidence below 0.5 and
  the closest plausible action.
- Copy names EXACTLY as the user wrote them. Never invent identifiers.
"""
