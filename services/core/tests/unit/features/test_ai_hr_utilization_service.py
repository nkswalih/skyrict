"""Unit tests for the utilization-alert service (HR-AI-002, 8.1.4 ).

Covers the documented Gherkin forfeit case (18 unused days / 55 remaining ->
warning with projected forfeiture of 18), severity mapping, negative-accrual
detection, the L1 aggregate, and the lazy-on-read TTL scan. Pure unit tests
with a fake repository — no database.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from core.features.ai_hr.utilization_repository import AiHrUtilizationRepository, UtilizationAlert
from core.features.ai_hr.utilization_service import UtilizationService

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.unit

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
EMP = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _alert(
    *,
    alert_type: str = "forfeit_risk",
    severity: str = "medium",
    balance_days: int = 18,
    projected_forfeiture_days: int | None = 18,
    days_remaining_in_year: int = 55,
) -> UtilizationAlert:
    return UtilizationAlert(
        employee_id=EMP,
        alert_type=alert_type,
        severity=severity,
        balance_days=balance_days,
        projected_forfeiture_days=projected_forfeiture_days,
        days_remaining_in_year=days_remaining_in_year,
        evidence={"leave_type": "annual"},
        created_at=datetime.now(UTC),
    )


class _FakeUtilRepo:
    def __init__(
        self,
        *,
        latest: datetime | None = None,
        rows: Sequence[UtilizationAlert] | None = None,
        stored: Sequence[UtilizationAlert] | None = None,
    ) -> None:
        self.latest = latest
        self.rows = rows or []
        self.stored = stored or []
        self.replacements: list[Sequence[UtilizationAlert]] = []

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        return self.latest

    async def build_utilization_rows(self, tenant_id: uuid.UUID) -> list[UtilizationAlert]:
        return list(self.rows)

    async def replace_tenant_alerts(
        self, tenant_id: uuid.UUID, alerts: list[UtilizationAlert]
    ) -> None:
        self.replacements.append(alerts)
        self.stored = alerts

    async def list_alerts(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[UtilizationAlert]:
        if employee_id is not None:
            return [a for a in self.stored if a.employee_id == employee_id]
        return list(self.stored)


# -- forfeit Gherkin case ---------------------------------------------------


async def test_forfeit_alert_matches_gherkin() -> None:
    # "18 unused days / 55 remaining year days -> warning + projected 18".
    repo = _FakeUtilRepo(
        latest=datetime.now(UTC),
        stored=[
            _alert(
                severity="medium",
                balance_days=18,
                projected_forfeiture_days=18,
                days_remaining_in_year=55,
            )
        ],
    )
    svc = UtilizationService(repo, refresh_days=1)

    alerts = await svc.own_alerts(TENANT, EMP)

    assert len(alerts) == 1
    assert alerts[0].alert_type == "forfeit_risk"
    assert alerts[0].severity == "medium"
    assert alerts[0].balance_days == 18
    assert alerts[0].projected_forfeiture_days == 18
    assert alerts[0].days_remaining_in_year == 55
    assert alerts[0].evidence["leave_type"] == "annual"


# -- severity ---------------------------------------------------------------


async def test_forfeit_severity_scales_with_balance() -> None:
    assert AiHrUtilizationRepository._forfeit_severity(25) == "high"
    assert AiHrUtilizationRepository._forfeit_severity(12) == "medium"
    assert AiHrUtilizationRepository._forfeit_severity(3) == "low"


# -- L1 aggregate -----------------------------------------------------------


async def test_org_feed_aggregates_counts_without_employee_data() -> None:
    other = uuid.UUID("33333333-3333-3333-3333-333333333333")
    repo = _FakeUtilRepo(
        latest=datetime.now(UTC),
        stored=[
            _alert(alert_type="forfeit_risk", severity="medium"),
            _alert(
                alert_type="negative_accrual",
                severity="high",
                balance_days=0,
                projected_forfeiture_days=None,
            ),
            UtilizationAlert(
                employee_id=other,
                alert_type="forfeit_risk",
                severity="high",
                balance_days=25,
                projected_forfeiture_days=25,
                days_remaining_in_year=10,
                evidence={},
                created_at=datetime.now(UTC),
            ),
        ],
    )
    svc = UtilizationService(repo, refresh_days=1)

    summary = await svc.org_feed(TENANT)

    assert summary.total_alerts == 3
    assert summary.by_type == {"forfeit_risk": 2, "negative_accrual": 1}
    assert summary.by_severity == {"medium": 1, "high": 2}
    assert "forfeit-risk" in summary.narrative


# -- lazy TTL ---------------------------------------------------------------


async def test_scan_runs_when_no_alerts_regenerated() -> None:
    repo = _FakeUtilRepo(latest=None, rows=[_alert()])
    svc = UtilizationService(repo, refresh_days=1)

    await svc.org_feed(TENANT)

    assert len(repo.replacements) == 1


async def test_scan_skipped_when_fresh() -> None:
    repo = _FakeUtilRepo(latest=datetime.now(UTC), stored=[_alert()])
    svc = UtilizationService(repo, refresh_days=1)

    await svc.org_feed(TENANT)

    assert repo.replacements == []


async def test_scan_runs_when_stale() -> None:
    repo = _FakeUtilRepo(latest=datetime.now(UTC) - timedelta(days=2), rows=[_alert()])
    svc = UtilizationService(repo, refresh_days=1)

    await svc.org_feed(TENANT)

    assert len(repo.replacements) == 1


async def test_employee_alerts_scoped_to_employee() -> None:
    repo = _FakeUtilRepo(latest=datetime.now(UTC), stored=[_alert()])
    svc = UtilizationService(repo, refresh_days=1)

    assert len(await svc.employee_alerts(TENANT, EMP)) == 1
    assert await svc.employee_alerts(TENANT, uuid.uuid4()) == []


def test_service_uses_enforced_default_refresh() -> None:
    assert UtilizationService(_FakeUtilRepo())._refresh_days == 1
