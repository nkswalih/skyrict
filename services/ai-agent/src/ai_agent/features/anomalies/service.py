"""Anomaly service - detection scan + review workflow (spec §4.3/§4.4).

``run_scan`` fetches the recent movement window through the gateway, runs
the deterministic rule set, dedupes against OPEN anomalies of the same
type, and persists new findings with audit events. ``review`` applies the
open -> resolved | dismissed | escalated transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.audit_events import (
    AI_ANOMALY_DETECTED,
    AI_ANOMALY_DISMISSED,
    AI_ANOMALY_ESCALATED,
    AI_ANOMALY_RESOLVED,
)
from ai_agent.features.anomalies.rules import detect_all
from skyrict_common.exceptions import ConflictError

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from ai_agent.core.audit_service import AuditService
    from ai_agent.db.anomaly_repository import AnomalyRepository
    from ai_agent.features.nl_query.gateway import InventoryGatewayPort

logger = structlog.get_logger("ai_agent.anomaly_service")

# status -> allowed source statuses (spec §4.4 workflow)
_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "resolved": ("open",),
    "dismissed": ("open",),
    "escalated": ("open", "resolved"),
}


@dataclass(frozen=True, slots=True)
class DetectionReport:
    detected: int
    duplicates_skipped: int


class AnomalyService:
    """Detection and review orchestration."""

    def __init__(
        self,
        *,
        gateway_factory: Callable[[], Awaitable[InventoryGatewayPort]],
        anomalies: AnomalyRepository,
        audit: AuditService,
    ) -> None:
        self._gateway_factory = gateway_factory
        self._anomalies = anomalies
        self._audit = audit

    async def run_scan(self, *, tenant_id: uuid.UUID) -> DetectionReport:
        """Detect anomalies over recent movements; dedupe open repeats."""
        gateway = await self._gateway_factory()
        movements = await gateway.list_movements()
        stock_levels = await gateway.get_stock_levels()
        findings = detect_all(movements, stock_levels=stock_levels)

        created = skipped = 0
        for finding in findings:
            # One OPEN anomaly per (type, product, warehouse) keeps feeds
            # actionable; resolved rows allow re-detection if the pattern
            # recurs on the same scope.
            if await self._anomalies.has_open(
                tenant_id=tenant_id,
                anomaly_type=finding.anomaly_type,
                product_id=finding.affected_product_id,
                warehouse_id=finding.affected_warehouse_id,
            ):
                skipped += 1
                continue
            row = await self._anomalies.create(
                tenant_id=tenant_id,
                anomaly_type=finding.anomaly_type,
                severity=finding.severity,
                title=finding.title,
                description=finding.description,
                affected_product_id=finding.affected_product_id,
                affected_warehouse_id=finding.affected_warehouse_id,
                related_movement_ids=finding.related_movement_ids,
            )
            await self._audit.log(
                action=AI_ANOMALY_DETECTED,
                tenant_id=tenant_id,
                input_payload={"anomaly_type": finding.anomaly_type},
                output_payload={"anomaly_id": str(row.id), "severity": finding.severity},
            )
            created += 1

        logger.info("anomaly_scan.completed", created=created, duplicates_skipped=skipped)
        return DetectionReport(detected=created, duplicates_skipped=skipped)

    async def review(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        anomaly_id: uuid.UUID,
        decision: str,
        note: str | None,
    ) -> None:
        """Apply a review transition to one anomaly (human investigates)."""
        if decision not in _TRANSITIONS:
            raise ValueError(f"invalid review decision {decision!r}")
        row = await self._anomalies.get(tenant_id=tenant_id, anomaly_id=anomaly_id)
        if row.status not in _TRANSITIONS[decision]:
            raise ConflictError(f"Cannot {decision} an anomaly in status '{row.status}'")
        await self._anomalies.record_review(
            row=row, status=decision, reviewed_by=user_id, resolution_note=note
        )
        decision_events = {
            "resolved": AI_ANOMALY_RESOLVED,
            "dismissed": AI_ANOMALY_DISMISSED,
            "escalated": AI_ANOMALY_ESCALATED,
        }
        await self._audit.log(
            action=decision_events[decision],
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"anomaly_id": str(anomaly_id)},
            output_payload={"decision": decision, "note": note},
        )
