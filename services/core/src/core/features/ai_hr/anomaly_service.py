"""Leave-pattern anomaly service (HR-AI-002, 8.2.1 — the anomaly inbox).

Lazy-on-read TTL scan (mirrors the quality/utilization services), then:

  - ``org_feed`` (L1, ``erp.hr.ai.read``): aggregate counts by anomaly type and
    severity plus a deterministic narrative — never per-person data.
  - ``employee_anomalies`` (L2, ``erp.hr.ai.individual``): one employee's
    findings with the stored title/description/evidence.
  - ``own_anomalies`` (self-scoped, ``erp.leave.self``): the employee's own
    findings for the portal surface — bound to the caller's employee record.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.features.ai_hr.anomaly_repository import LeaveAnomaly


class AiHrAnomalyRepositoryPort(Protocol):
    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None: ...

    async def build_anomaly_rows(self, tenant_id: uuid.UUID) -> list[LeaveAnomaly]: ...

    async def replace_tenant_anomalies(
        self, tenant_id: uuid.UUID, rows: list[LeaveAnomaly]
    ) -> None: ...

    async def list_anomalies(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[LeaveAnomaly]: ...


@dataclass(frozen=True, slots=True)
class AnomalyOrgSummary:
    """L1 aggregates across the tenant (no per-person data)."""

    total_anomalies: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    generated_at: datetime
    narrative: str


class AnomalyService:
    def __init__(
        self,
        repository: AiHrAnomalyRepositoryPort,
        refresh_days: int = 7,
    ) -> None:
        self._repository = repository
        self._refresh_days = refresh_days

    async def _ensure_scan(self, tenant_id: uuid.UUID) -> None:
        latest = await self._repository.latest_generated_at(tenant_id)
        now = datetime.now(UTC)
        stale = latest is None or (now - latest) >= timedelta(days=self._refresh_days)
        if stale:
            rows = await self._repository.build_anomaly_rows(tenant_id)
            await self._repository.replace_tenant_anomalies(tenant_id, rows)

    async def org_feed(self, tenant_id: uuid.UUID) -> AnomalyOrgSummary:
        await self._ensure_scan(tenant_id)
        anomalies = await self._repository.list_anomalies(tenant_id)
        return self._build_summary(anomalies)

    async def employee_anomalies(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[LeaveAnomaly]:
        await self._ensure_scan(tenant_id)
        return await self._repository.list_anomalies(tenant_id, employee_id=employee_id)

    async def own_anomalies(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[LeaveAnomaly]:
        """Self-scoped feed for the employee's portal."""
        await self._ensure_scan(tenant_id)
        return await self._repository.list_anomalies(tenant_id, employee_id=employee_id)

    @staticmethod
    def _build_summary(anomalies: Sequence[LeaveAnomaly]) -> AnomalyOrgSummary:
        by_type = Counter(a.anomaly_type for a in anomalies)
        by_severity = Counter(a.severity for a in anomalies)
        narrative = (
            f"{len(anomalies)} open leave anomaly(-ies): "
            f"{by_type.get('leave_overuse', 0)} overuse, "
            f"{by_type.get('frequent_absence', 0)} frequent-absence."
        )
        return AnomalyOrgSummary(
            total_anomalies=len(anomalies),
            by_type=dict(by_type),
            by_severity=dict(by_severity),
            generated_at=anomalies[0].created_at if anomalies else datetime.now(UTC),
            narrative=narrative,
        )


__all__ = [
    "AiHrAnomalyRepositoryPort",
    "AnomalyOrgSummary",
    "AnomalyService",
    "LeaveAnomaly",
]
