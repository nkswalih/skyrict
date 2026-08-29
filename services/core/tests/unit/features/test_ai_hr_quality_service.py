"""Unit tests for the HR data-quality scorer (HR-AI-002, 8.1.3).

Pure unit tests with a fake repository: weighted scoring/grade derivation,
the L1 org KPI aggregation, and the lazy-on-read TTL recalc. No database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from core.features.ai_hr.quality_repository import EmployeeQuality
from core.features.ai_hr.quality_service import QualityService, _score_row

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.unit

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEPT_A = uuid.UUID("33333333-3333-3333-3333-333333333333")
EMP_A = uuid.UUID("22222222-2222-2222-2222-222222222222")
EMP_B = uuid.UUID("44444444-4444-4444-4444-444444444444")


def _row(
    employee_id: uuid.UUID = EMP_A,
    *,
    department_id: uuid.UUID | None = DEPT_A,
    department_name: str | None = "Engineering",
    mandatory_missing: list[str] | None = None,
    contact_issues: list[str] | None = None,
    document_issues: list[str] | None = None,
) -> EmployeeQuality:
    return EmployeeQuality(
        employee_id=employee_id,
        department_id=department_id,
        mandatory_missing=mandatory_missing or [],
        contact_issues=contact_issues or [],
        document_issues=document_issues or [],
        first_name="Ada",
        last_name="Lovelace",
        department_name=department_name,
    )


class _FakeQualityRepo:
    def __init__(
        self,
        *,
        latest: datetime | None = None,
        rows: list[EmployeeQuality] | None = None,
        stored: list[EmployeeQuality] | None = None,
    ) -> None:
        self.latest = latest
        self.rows = rows or []
        self.stored = stored or []
        self.upserts: list[list[EmployeeQuality]] = []

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        return self.latest

    async def build_quality_rows(self, tenant_id: uuid.UUID) -> list[EmployeeQuality]:
        return self.rows

    async def upsert_quality(self, tenant_id: uuid.UUID, rows: Sequence[EmployeeQuality]) -> None:
        self.upserts.append(list(rows))
        self.stored = list(rows)

    async def list_quality(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[EmployeeQuality]:
        if employee_id is not None:
            return [r for r in self.stored if r.employee_id == employee_id]
        return self.stored


# -- scoring ----------------------------------------------------------------


def test_score_row_assigns_max_grade_for_complete_employee() -> None:
    scored = _score_row(_row())
    assert scored.score == pytest.approx(1.0)
    assert scored.grade == "A"
    assert scored.mandatory_score == pytest.approx(0.5)
    assert scored.contact_score == pytest.approx(0.25)
    assert scored.document_score == pytest.approx(0.25)


def test_score_row_punishes_missing_mandatory_fields() -> None:
    scored = _score_row(_row(mandatory_missing=["missing_email", "missing_phone"]))
    assert scored.mandatory_score == pytest.approx(0.5 * (3 / 5))
    assert scored.score < 0.9
    assert scored.grade in ("B", "C", "D", "F")


def test_score_row_downgrades_on_invalid_contact_issues() -> None:
    scored = _score_row(_row(contact_issues=["invalid_email", "invalid_phone"]))
    assert scored.contact_score == pytest.approx(0.25 * (1 / 3), abs=1e-4)
    assert scored.grade != "A"


def test_score_row_downgrades_on_expired_documents() -> None:
    scored = _score_row(
        _row(
            document_issues=[
                "expired_document:work_permit",
                "missing_document:passport",
            ]
        )
    )
    assert scored.document_score == pytest.approx(0.25 * (2 / 4), abs=1e-4)
    assert scored.grade != "A"


# -- KPI aggregation --------------------------------------------------------


async def test_org_kpi_aggregates_by_department_and_grade() -> None:
    a = _score_row(_row(EMP_A, mandatory_missing=["missing_email"]))
    b = _score_row(
        _row(
            EMP_B,
            department_id=None,
            department_name=None,
            mandatory_missing=["missing_email", "missing_phone", "missing_job_title"],
        )
    )
    repo = _FakeQualityRepo(latest=datetime.now(UTC), stored=[a, b])

    svc = QualityService(repo, refresh_days=7)
    kpi = await svc.org_kpi(TENANT)

    assert kpi.total_scored == 2
    assert 0.0 < kpi.average_score < 1.0
    assert kpi.grade_distribution["A"] == 1
    assert {d.department_name for d in kpi.department_averages} == {
        "Unassigned",
        "Engineering",
    }
    assert "Average data-quality score" in kpi.narrative


async def test_org_kpi_empty_tenant() -> None:
    repo = _FakeQualityRepo(latest=datetime.now(UTC), stored=[])
    svc = QualityService(repo, refresh_days=7)

    kpi = await svc.org_kpi(TENANT)

    assert kpi.total_scored == 0
    assert kpi.average_score == 0.0
    assert kpi.grade_distribution == {}


# -- lazy TTL recalc --------------------------------------------------------


async def test_recalc_runs_when_no_scored_run_exists() -> None:
    rows = [_row()]
    repo = _FakeQualityRepo(latest=None, rows=rows)
    svc = QualityService(repo, refresh_days=7)

    await svc.org_kpi(TENANT)

    assert len(repo.upserts) == 1
    assert repo.upserts[0][0].grade == "A"


async def test_recalc_skipped_when_run_is_fresh() -> None:
    repo = _FakeQualityRepo(latest=datetime.now(UTC), stored=[_row()])
    svc = QualityService(repo, refresh_days=7)

    await svc.org_kpi(TENANT)

    assert repo.upserts == []


async def test_recalc_runs_when_run_is_stale() -> None:
    repo = _FakeQualityRepo(latest=datetime.now(UTC) - timedelta(days=8), rows=[_row()])
    svc = QualityService(repo, refresh_days=7)

    await svc.org_kpi(TENANT)

    assert len(repo.upserts) == 1


async def test_employee_quality_returns_none_when_not_scored() -> None:
    repo = _FakeQualityRepo(latest=datetime.now(UTC), stored=[])
    svc = QualityService(repo, refresh_days=7)

    assert await svc.employee_quality(TENANT, EMP_A) is None
