"""Utilization-alert service (HR-AI-002, 8.1.4).

Lazy-on-read TTL scan (mirrors the quality/attrition services), then:

  - ``org_feed`` (L1, ``erp.hr.ai.read``): aggregate counts by alert type and
    severity plus a deterministic narrative — never per-person data.
  - ``employee_alerts`` (L2, ``erp.hr.ai.individual``): one employee's alerts.
  - ``own_alerts`` (self-scoped, ``erp.leave.self``): the employee's own feed
    for the portal surface — bound to the caller's linked employee record.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.features.ai_hr.utilization_repository import UtilizationAlert


class AiHrUtilizationRepositoryPort(Protocol):
    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None: ...

    async def build_utilization_rows(self, tenant_id: uuid.UUID) -> list[UtilizationAlert]: ...

    async def replace_tenant_alerts(
        self, tenant_id: uuid.UUID, alerts: list[UtilizationAlert]
    ) -> None: ...

    async def list_alerts(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[UtilizationAlert]: ...


@dataclass(frozen=True, slots=True)
class UtilizationOrgSummary:
    """L1 aggregates across the tenant (no per-person data)."""

    total_alerts: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    generated_at: datetime
    narrative: str


class UtilizationService:
    def __init__(
        self,
        repository: AiHrUtilizationRepositoryPort,
        refresh_days: int = 1,
    ) -> None:
        self._repository = repository
        self._refresh_days = refresh_days

    async def _ensure_scan(self, tenant_id: uuid.UUID) -> None:
        latest = await self._repository.latest_generated_at(tenant_id)
        now = datetime.now(UTC)
        stale = latest is None or (now - latest) >= timedelta(days=self._refresh_days)
        if stale:
            rows = await self._repository.build_utilization_rows(tenant_id)
            await self._repository.replace_tenant_alerts(tenant_id, rows)

    async def org_feed(self, tenant_id: uuid.UUID) -> UtilizationOrgSummary:
        await self._ensure_scan(tenant_id)
        alerts = await self._repository.list_alerts(tenant_id)
        return self._build_summary(alerts)

    async def employee_alerts(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[UtilizationAlert]:
        await self._ensure_scan(tenant_id)
        return await self._repository.list_alerts(tenant_id, employee_id=employee_id)

    async def own_alerts(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[UtilizationAlert]:
        """Self-scoped feed for the employee's portal."""
        await self._ensure_scan(tenant_id)
        return await self._repository.list_alerts(tenant_id, employee_id=employee_id)

    @staticmethod
    def _build_summary(alerts: Sequence[UtilizationAlert]) -> UtilizationOrgSummary:
        by_type = Counter(a.alert_type for a in alerts)
        by_severity = Counter(a.severity for a in alerts)
        narrative = (
            f"{len(alerts)} active utilization alert(s): "
            f"{by_type.get('forfeit_risk', 0)} forfeit-risk, "
            f"{by_type.get('negative_accrual', 0)} negative-accrual."
        )
        return UtilizationOrgSummary(
            total_alerts=len(alerts),
            by_type=dict(by_type),
            by_severity=dict(by_severity),
            generated_at=alerts[0].created_at if alerts else datetime.now(UTC),
            narrative=narrative,
        )


__all__ = [
    "AiHrUtilizationRepositoryPort",
    "UtilizationAlert",
    "UtilizationOrgSummary",
    "UtilizationService",
]
