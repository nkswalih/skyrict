"""Restock service - scan and approval workflow (spec §3.2/§3.3).

``run_scan`` is the deterministic daily/manual job: fetch catalogs, compute
drafts for every product/warehouse pair at-or-below reorder point, skip
pairs that already have a PENDING suggestion (spec §3.4 idempotency), insert
the rest. ``review`` applies approve/reject with audit. Rate limiting lives
in the router layer (per-scope keys); this service owns business rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.exc import IntegrityError

from ai_agent.core.audit_events import (
    AI_SUGGESTION_APPROVED,
    AI_SUGGESTION_CREATED,
    AI_SUGGESTION_REJECTED,
)
from ai_agent.features.restock.calculator import compute_suggestion
from skyrict_common.exceptions import ConflictError

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from ai_agent.core.audit_service import AuditService
    from ai_agent.db.suggestion_repository import SuggestionRepository
    from ai_agent.features.nl_query.gateway import InventoryGatewayPort, ProductRef

logger = structlog.get_logger("ai_agent.restock_service")


@dataclass(frozen=True, slots=True)
class ScanReport:
    """Outcome summary of one scan run."""

    created: int
    skipped_pending: int
    considered: int


class RestockService:
    """Scan-and-suggest plus human review orchestration."""

    def __init__(
        self,
        *,
        gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]],
        suggestions: SuggestionRepository,
        audit: AuditService,
    ) -> None:
        self._gateway_factory = gateway_factory
        self._suggestions = suggestions
        self._audit = audit

    async def run_scan(self, *, tenant_id: uuid.UUID) -> ScanReport:
        """Compute and persist pending suggestions for below-reorder stock."""
        gateway = await self._gateway_factory()
        products, levels = await gateway.list_products(), await gateway.get_stock_levels()

        # Fetch recent movements for 4-factor confidence scoring (spec 3.2).
        movements = await gateway.list_movements()

        qty_by_pair: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = {}
        for row in levels:
            key = (row.product_id, row.warehouse_id)
            qty_by_pair[key] = qty_by_pair.get(key, Decimal(0)) + row.qty_on_hand

        product_by_id: dict[uuid.UUID, ProductRef] = {p.id: p for p in products}
        pending_rows, _total = await self._suggestions.list_by_status(
            tenant_id=tenant_id, status="pending"
        )
        pending_pairs = {(row.product_id, row.warehouse_id) for row in pending_rows}

        created = skipped = 0
        for (product_id, warehouse_id), qty in sorted(qty_by_pair.items()):
            product = product_by_id.get(product_id)
            if product is None or qty > product.reorder_point:
                continue  # unknown id or healthy stock
            if (product_id, warehouse_id) in pending_pairs:
                skipped += 1
                continue
            draft = compute_suggestion(
                product=product,
                warehouse_id=warehouse_id,
                qty_on_hand=qty,
                movements=movements,
            )
            try:
                await self._suggestions.create_pending(
                    tenant_id=tenant_id,
                    product_id=draft.product_id,
                    warehouse_id=draft.warehouse_id,
                    current_stock=draft.current_stock,
                    reorder_point=draft.reorder_point,
                    suggested_qty=draft.suggested_qty,
                    estimated_cost=draft.estimated_cost,
                    reason=draft.reason,
                    confidence=draft.confidence,
                )
            except IntegrityError:
                # Raced with a concurrent scan; the DB unique index keeps the
                # "one pending per pair" invariant - count as skipped.
                skipped += 1
                continue
            await self._audit.log(
                action=AI_SUGGESTION_CREATED,
                tenant_id=tenant_id,
                input_payload={
                    "product_id": str(product_id),
                    "warehouse_id": str(warehouse_id),
                    "current_stock": str(qty),
                },
                output_payload={"suggested_qty": str(draft.suggested_qty)},
            )
            created += 1

        logger.info(
            "restock_scan.completed",
            considered=len(qty_by_pair),
            created=created,
            skipped_pending=skipped,
        )
        return ScanReport(created=created, skipped_pending=skipped, considered=len(qty_by_pair))

    async def review(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        decision: str,
        note: str | None,
    ) -> None:
        """Approve or reject one pending suggestion (human decides, spec §1.4)."""
        if decision not in ("approved", "rejected"):
            raise ValueError(f"invalid review decision {decision!r}")
        row = await self._suggestions.get_for_review(
            tenant_id=tenant_id, suggestion_id=suggestion_id
        )
        if row.status != "pending":
            raise ConflictError(
                f"Suggestion is already {row.status} - only pending rows are reviewable"
            )
        await self._suggestions.record_review(
            row=row, status=decision, reviewed_by=user_id, review_note=note
        )
        action = AI_SUGGESTION_APPROVED if decision == "approved" else AI_SUGGESTION_REJECTED
        await self._audit.log(
            action=action,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"suggestion_id": str(suggestion_id)},
            output_payload={"decision": decision, "note": note},
        )
