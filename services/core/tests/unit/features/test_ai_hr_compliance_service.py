"""Unit tests for the compliance finding service (HR-AI-001, Unit C).

The pure rule engine lives in skyrict_common and is unit-tested there; these
tests exercise the service layer: the L1 aggregate, the L2 per-employee
scoping, the lazy-on-read TTL scan, and the status lifecycle with its audit
events and transition guardrails.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core.features.ai_hr.compliance_repository import ComplianceFindingRow
from core.features.ai_hr.compliance_service import ComplianceService
from core.features.ai_hr.models.compliance_check import ComplianceStatus

pytestmark = pytest.mark.unit

TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
E1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
E2 = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _finding(
    *,
    employee_id: uuid.UUID | None = E1,
    check_type: str = "document_expiry",
    severity: str = "medium",
    status: str = ComplianceStatus.OPEN,
) -> ComplianceFindingRow:
    return ComplianceFindingRow(
        employee_id=employee_id,
        check_type=check_type,
        severity=severity,
        owner_rule="compliance",
        status=status,
        title="Document is expiring",
        description="A work permit expires soon.",
        evidence={"document_type": "WORK_PERMIT"},
        created_at=datetime.now(UTC),
        check_id=uuid.uuid4(),
    )


class _FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def log(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class _FakeComplianceRepo:
    def __init__(
        self,
        *,
        latest: datetime | None = None,
        rows: list[ComplianceFindingRow] | None = None,
        stored: list[ComplianceFindingRow] | None = None,
    ) -> None:
        self.latest = latest
        self.rows = rows or []
        self.stored = stored or []
        self.replacements: list[list[ComplianceFindingRow]] = []

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        return self.latest

    async def build_compliance_rows(self, tenant_id: uuid.UUID) -> list[ComplianceFindingRow]:
        return list(self.rows)

    async def replace_tenant_findings(
        self, tenant_id: uuid.UUID, rows: list[ComplianceFindingRow]
    ) -> None:
        self.replacements.append(rows)
        self.stored = rows

    async def list_findings(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[ComplianceFindingRow]:
        if employee_id is not None:
            return [f for f in self.stored if f.employee_id == employee_id]
        return list(self.stored)

    async def get_finding(
        self, tenant_id: uuid.UUID, check_id: uuid.UUID
    ) -> ComplianceFindingRow | None:
        for f in self.stored:
            if f.check_id == check_id:
                return f
        return None

    async def set_status(
        self,
        tenant_id: uuid.UUID,
        check_id: uuid.UUID,
        *,
        status: str,
        owner_user_id: uuid.UUID | None = None,
    ) -> ComplianceFindingRow | None:
        idx = next(
            (i for i, f in enumerate(self.stored) if f.check_id == check_id),
            None,
        )
        if idx is None:
            return None
        current = self.stored[idx]
        updated = ComplianceFindingRow(
            employee_id=current.employee_id,
            check_type=current.check_type,
            severity=current.severity,
            owner_rule=current.owner_rule,
            status=status,
            title=current.title,
            description=current.description,
            evidence=current.evidence,
            created_at=current.created_at,
            check_id=current.check_id,
            owner_user_id=owner_user_id if owner_user_id else current.owner_user_id,
        )
        self.stored[idx] = updated
        return updated


async def test_org_feed_aggregates_types_severity_and_open() -> None:
    repo = _FakeComplianceRepo(
        latest=datetime.now(UTC),
        stored=[
            _finding(check_type="document_expiry", severity="medium"),
            _finding(
                employee_id=E2,
                check_type="training_overdue",
                severity="high",
                status=ComplianceStatus.ACKNOWLEDGED,
            ),
            _finding(
                employee_id=E2,
                check_type="contract_missing_field",
                severity="low",
                status=ComplianceStatus.RESOLVED,
            ),
        ],
    )
    summary = await ComplianceService(repo, refresh_days=7).org_feed(TENANT)
    assert summary.total_findings == 3
    assert summary.open_findings == 1
    assert summary.by_type == {
        "document_expiry": 1,
        "training_overdue": 1,
        "contract_missing_field": 1,
    }
    assert summary.by_severity == {"medium": 1, "high": 1, "low": 1}
    assert "1 open compliance finding" in summary.narrative
    assert [
        (g.check_type, g.weighted_open_score, g.open_count, g.total_count)
        for g in summary.risk_ranked
    ] == [
        ("document_expiry", 2, 1, 1),
        ("contract_missing_field", 0, 0, 1),
        ("training_overdue", 0, 0, 1),
    ]


async def test_org_feed_abstains_when_empty() -> None:
    repo = _FakeComplianceRepo(latest=datetime.now(UTC), stored=[])
    summary = await ComplianceService(repo, refresh_days=7).org_feed(TENANT)
    assert summary.total_findings == 0
    assert summary.open_findings == 0
    assert summary.by_type == {}
    assert summary.by_severity == {}
    assert summary.risk_ranked == []


async def test_employee_findings_scopes_by_employee() -> None:
    repo = _FakeComplianceRepo(
        latest=datetime.now(UTC),
        stored=[
            _finding(employee_id=E1),
            _finding(employee_id=E2, check_type="training_overdue"),
        ],
    )
    svc = ComplianceService(repo, refresh_days=7)
    assert len(await svc.employee_findings(TENANT, E1)) == 1
    assert len(await svc.employee_findings(TENANT, E2)) == 1


async def test_scan_skipped_when_fresh() -> None:
    repo = _FakeComplianceRepo(latest=datetime.now(UTC), stored=[_finding()])
    await ComplianceService(repo, refresh_days=7).org_feed(TENANT)
    assert repo.replacements == []


async def test_scan_runs_when_stale_or_absent() -> None:
    stale = _FakeComplianceRepo(latest=datetime.now(UTC) - timedelta(days=8), rows=[_finding()])
    await ComplianceService(stale, refresh_days=7).org_feed(TENANT)
    assert len(stale.replacements) == 1

    absent = _FakeComplianceRepo(latest=None, rows=[_finding()])
    await ComplianceService(absent, refresh_days=7).org_feed(TENANT)
    assert len(absent.replacements) == 1


async def test_set_status_open_to_acknowledged_audits() -> None:
    target = _finding()
    repo = _FakeComplianceRepo(latest=datetime.now(UTC), stored=[target])
    audit = _FakeAudit()
    actor = uuid.uuid4()
    updated = await ComplianceService(repo, refresh_days=7, audit=audit).set_status(
        TENANT, target.check_id, status=ComplianceStatus.ACKNOWLEDGED, actor_user_id=actor
    )
    assert updated.status == ComplianceStatus.ACKNOWLEDGED
    assert audit.events[0]["action"] == "hr.ai.compliance.acknowledged"
    assert audit.events[0]["target"] == f"compliance:{target.check_id}"
    assert audit.events[0]["user_id"] == str(actor)
    assert audit.events[0]["details"] == {"from": "open", "to": "acknowledged"}


async def test_set_status_acknowledged_to_resolved_audits() -> None:
    target = _finding(status=ComplianceStatus.ACKNOWLEDGED)
    repo = _FakeComplianceRepo(latest=datetime.now(UTC), stored=[target])
    audit = _FakeAudit()
    updated = await ComplianceService(repo, refresh_days=7, audit=audit).set_status(
        TENANT, target.check_id, status=ComplianceStatus.RESOLVED, actor_user_id=uuid.uuid4()
    )
    assert updated.status == ComplianceStatus.RESOLVED
    assert audit.events[0]["action"] == "hr.ai.compliance.resolved"


async def test_set_status_open_can_jump_directly_to_resolved() -> None:
    target = _finding(status=ComplianceStatus.OPEN)
    repo = _FakeComplianceRepo(latest=datetime.now(UTC), stored=[target])
    updated = await ComplianceService(repo, refresh_days=7).set_status(
        TENANT, target.check_id, status=ComplianceStatus.RESOLVED, actor_user_id=uuid.uuid4()
    )
    assert updated.status == ComplianceStatus.RESOLVED


async def test_set_status_rejects_backwards_or_disallowed_transition() -> None:
    from core.core.exceptions import IllegalStateTransitionError

    resolved = _finding(status=ComplianceStatus.RESOLVED)
    repo = _FakeComplianceRepo(latest=datetime.now(UTC), stored=[resolved])
    svc = ComplianceService(repo, refresh_days=7)
    with pytest.raises(IllegalStateTransitionError):
        await svc.set_status(
            TENANT,
            resolved.check_id,
            status=ComplianceStatus.ACKNOWLEDGED,
            actor_user_id=uuid.uuid4(),
        )


async def test_set_status_unknown_status_rejected() -> None:
    from core.core.exceptions import IllegalStateTransitionError

    target = _finding()
    repo = _FakeComplianceRepo(latest=datetime.now(UTC), stored=[target])
    svc = ComplianceService(repo, refresh_days=7)
    with pytest.raises(IllegalStateTransitionError):
        await svc.set_status(TENANT, target.check_id, status="banana", actor_user_id=uuid.uuid4())


async def test_set_status_missing_finding_raises_not_found() -> None:
    from core.core.exceptions import NotFoundError

    repo = _FakeComplianceRepo(latest=datetime.now(UTC))
    svc = ComplianceService(repo, refresh_days=7)
    with pytest.raises(NotFoundError):
        await svc.set_status(
            TENANT, uuid.uuid4(), status=ComplianceStatus.RESOLVED, actor_user_id=uuid.uuid4()
        )
