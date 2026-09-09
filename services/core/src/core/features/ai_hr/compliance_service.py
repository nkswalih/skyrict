"""Compliance finding service (HR-AI-001, Unit C — the compliance inbox).

Lazy-on-read TTL scan — exactly the leave/payroll inbox pattern — then:

  - ``org_feed`` (L1, ``erp.hr.ai.read``): aggregate counts by check type /
    severity plus a deterministic narrative; never per-person data.
  - ``employee_findings`` (L2, ``erp.hr.ai.individual``): one employee's
    findings with stored title/description/evidence.
  - ``set_status`` (``erp.hr.ai.acknowledge``): moves a finding along
    ``open -> acknowledged|resolved`` and emits an audit event.

The scan rebuilds the tenant inbox from current people + documents each time
(replace-tenant regen), so dispositions survive only until the next scan —
the same documented tradeoff as the leave/payroll inboxes.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from core.core.audit_events import (
    HR_AI_COMPLIANCE_ACKNOWLEDGED,
    HR_AI_COMPLIANCE_RESOLVED,
)
from core.core.exceptions import IllegalStateTransitionError, NotFoundError
from core.features.ai_hr.compliance_repository import ComplianceFindingRow
from core.features.ai_hr.models.compliance_check import (
    ComplianceStatus,
)

_COMPLIANCE_DISPOSITION_EVENTS: dict[str, str] = {
    ComplianceStatus.ACKNOWLEDGED: HR_AI_COMPLIANCE_ACKNOWLEDGED,
    ComplianceStatus.RESOLVED: HR_AI_COMPLIANCE_RESOLVED,
}

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ComplianceStatus.OPEN: frozenset({ComplianceStatus.ACKNOWLEDGED, ComplianceStatus.RESOLVED}),
    ComplianceStatus.ACKNOWLEDGED: frozenset({ComplianceStatus.RESOLVED}),
    ComplianceStatus.RESOLVED: frozenset(),
}

_SEVERITY_WEIGHTS: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class AiHrComplianceRepositoryPort(Protocol):
    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None: ...

    async def build_compliance_rows(self, tenant_id: uuid.UUID) -> list[ComplianceFindingRow]: ...

    async def replace_tenant_findings(
        self, tenant_id: uuid.UUID, rows: list[ComplianceFindingRow]
    ) -> None: ...

    async def list_findings(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[ComplianceFindingRow]: ...

    async def get_finding(
        self, tenant_id: uuid.UUID, check_id: uuid.UUID
    ) -> ComplianceFindingRow | None: ...

    async def set_status(
        self,
        tenant_id: uuid.UUID,
        check_id: uuid.UUID,
        *,
        status: str,
        owner_user_id: uuid.UUID | None = None,
    ) -> ComplianceFindingRow | None: ...


@dataclass(frozen=True, slots=True)
class ComplianceRiskGroup:
    """Severity-weighted risk for one check type — drives the L3 rank order."""

    check_type: str
    weighted_open_score: int
    open_count: int
    total_count: int


@dataclass(frozen=True, slots=True)
class ComplianceOrgSummary:
    """L1 aggregates across the tenant (no per-person data)."""

    total_findings: int
    open_findings: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    risk_ranked: list[ComplianceRiskGroup]
    generated_at: datetime
    narrative: str


class ComplianceService:
    def __init__(
        self,
        repository: AiHrComplianceRepositoryPort,
        refresh_days: int = 7,
        audit: Any = None,
    ) -> None:
        self._repository = repository
        self._refresh_days = refresh_days
        self._audit = audit

    async def _ensure_scan(self, tenant_id: uuid.UUID) -> None:
        latest = await self._repository.latest_generated_at(tenant_id)
        now = datetime.now(UTC)
        stale = latest is None or (now - latest) >= timedelta(days=self._refresh_days)
        if stale:
            rows = await self._repository.build_compliance_rows(tenant_id)
            await self._repository.replace_tenant_findings(tenant_id, rows)

    async def org_feed(self, tenant_id: uuid.UUID) -> ComplianceOrgSummary:
        await self._ensure_scan(tenant_id)
        findings = await self._repository.list_findings(tenant_id)
        return self._build_summary(findings)

    async def employee_findings(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[ComplianceFindingRow]:
        await self._ensure_scan(tenant_id)
        return await self._repository.list_findings(tenant_id, employee_id=employee_id)

    async def set_status(
        self,
        tenant_id: uuid.UUID,
        check_id: uuid.UUID,
        *,
        status: str,
        actor_user_id: uuid.UUID,
    ) -> ComplianceFindingRow:
        """Apply a status transition and record it in the audit log."""
        if status not in _COMPLIANCE_DISPOSITION_EVENTS:
            raise IllegalStateTransitionError(f"unknown compliance status '{status}' for finding")
        await self._ensure_scan(tenant_id)
        current = await self._repository.get_finding(tenant_id, check_id)
        if current is None:
            raise NotFoundError(f"no compliance finding {check_id}")
        if status not in _ALLOWED_TRANSITIONS.get(current.status, frozenset()):
            raise IllegalStateTransitionError(
                f"cannot move compliance finding {check_id} from '{current.status}' to '{status}'"
            )
        updated = await self._repository.set_status(
            tenant_id,
            check_id,
            status=status,
            owner_user_id=actor_user_id,
        )
        if updated is None:
            raise NotFoundError(f"no compliance finding {check_id}")
        if self._audit is not None:
            await self._audit.log(
                action=_COMPLIANCE_DISPOSITION_EVENTS[status],
                target=f"compliance:{check_id}",
                tenant_id=str(tenant_id),
                user_id=str(actor_user_id),
                details={"from": current.status, "to": status},
            )
        return updated

    @staticmethod
    def _build_summary(
        findings: Sequence[ComplianceFindingRow],
    ) -> ComplianceOrgSummary:
        by_type = Counter(f.check_type for f in findings)
        by_severity = Counter(f.severity for f in findings)
        open_count = sum(1 for f in findings if f.status == ComplianceStatus.OPEN)

        groups: dict[str, list[int]] = {}
        for f in findings:
            groups.setdefault(f.check_type, []).append(
                _SEVERITY_WEIGHTS.get(f.severity, 1) if f.status == ComplianceStatus.OPEN else 0
            )
        risk_ranked = sorted(
            (
                ComplianceRiskGroup(
                    check_type=check_type,
                    weighted_open_score=sum(scores),
                    open_count=sum(1 for s in scores if s),
                    total_count=len(scores),
                )
                for check_type, scores in groups.items()
            ),
            key=lambda g: (-g.weighted_open_score, g.check_type),
        )

        narrative = (
            f"{open_count} open compliance finding(-ies): "
            f"{by_type.get('document_expiry', 0)} document expiries, "
            f"{by_type.get('training_overdue', 0)} overdue training, "
            f"{by_type.get('contract_missing_field', 0)} missing record fields; "
            f"{by_severity.get('high', 0)} high, "
            f"{by_severity.get('critical', 0)} critical."
        )
        return ComplianceOrgSummary(
            total_findings=len(findings),
            open_findings=open_count,
            by_type=dict(by_type),
            by_severity=dict(by_severity),
            risk_ranked=risk_ranked,
            generated_at=findings[0].created_at if findings else datetime.now(UTC),
            narrative=narrative,
        )


__all__ = [
    "AiHrComplianceRepositoryPort",
    "ComplianceFindingRow",
    "ComplianceOrgSummary",
    "ComplianceRiskGroup",
    "ComplianceService",
]
