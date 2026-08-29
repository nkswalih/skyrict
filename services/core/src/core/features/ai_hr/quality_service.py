"""Data-quality scoring service (HR-AI-002, 8.1.3).

Computes the weighted per-employee quality score — mandatory 0.50, contact
0.25, document 0.25 — converts it to an A-F grade, persists one run
idempotently, and exposes:

  - ``org_kpi`` (L1, ``erp.hr.ai.read``): tenant/department aggregates and a
    deterministic narrative; no per-person values.
  - ``employee_quality`` (L2, ``erp.hr.ai.individual``): the per-employee
    drill-down for the worst offenders.

Recompute is lazy-on-read (TTL refresh), mirroring the attrition service: it
re-scores only when no run exists or the latest is older than the interval, and
always serves the stored run so the admin panel renders with an "as of" label.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.features.ai_hr.quality_repository import EmployeeQuality

# Sub-bucket denominators (a signal's presence lowers the bucket fraction).
_MANDATORY_SIGNALS = 5
_CONTACT_SIGNALS = 3
_DOCUMENT_TYPES = 4

# Weights (documented in the spec and the table's model docstring).
_W_MANDATORY = 0.50
_W_CONTACT = 0.25
_W_DOCUMENT = 0.25


class AiHrQualityRepositoryPort(Protocol):
    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None: ...

    async def build_quality_rows(self, tenant_id: uuid.UUID) -> list[EmployeeQuality]: ...

    async def upsert_quality(
        self, tenant_id: uuid.UUID, rows: Sequence[EmployeeQuality]
    ) -> None: ...

    async def list_quality(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[EmployeeQuality]: ...


def _score_row(q: EmployeeQuality) -> EmployeeQuality:
    """Fill in the sub-scores, total score, and grade for one quality row."""
    mandatory_frac = max(0.0, 1.0 - len(q.mandatory_missing) / _MANDATORY_SIGNALS)
    contact_frac = max(0.0, 1.0 - len(q.contact_issues) / _CONTACT_SIGNALS)
    failed_doc_types = {issue.split(":", 1)[1] for issue in q.document_issues if ":" in issue}
    document_frac = max(0.0, 1.0 - len(failed_doc_types) / _DOCUMENT_TYPES)

    mandatory_score = round(mandatory_frac * _W_MANDATORY, 4)
    contact_score = round(contact_frac * _W_CONTACT, 4)
    document_score = round(document_frac * _W_DOCUMENT, 4)
    total = round(mandatory_score + contact_score + document_score, 4)

    if total >= 0.9:
        grade = "A"
    elif total >= 0.75:
        grade = "B"
    elif total >= 0.6:
        grade = "C"
    elif total >= 0.5:
        grade = "D"
    else:
        grade = "F"

    return EmployeeQuality(
        employee_id=q.employee_id,
        department_id=q.department_id,
        mandatory_missing=q.mandatory_missing,
        contact_issues=q.contact_issues,
        document_issues=q.document_issues,
        mandatory_score=mandatory_score,
        contact_score=contact_score,
        document_score=document_score,
        score=total,
        grade=grade,
        generated_at=q.generated_at,
        employee_number=q.employee_number,
        first_name=q.first_name,
        last_name=q.last_name,
        department_name=q.department_name,
    )


@dataclass(frozen=True, slots=True)
class QualityOrgKpi:
    """L1 aggregates across the tenant (no per-person data)."""

    total_scored: int
    average_score: float
    grade_distribution: dict[str, int]
    department_averages: list[DepartmentQuality]
    generated_at: datetime
    narrative: str


@dataclass(frozen=True, slots=True)
class DepartmentQuality:
    department_name: str
    average_score: float
    low_quality_count: int  # grade in C..F
    scored: int


class QualityService:
    def __init__(
        self,
        repository: AiHrQualityRepositoryPort,
        refresh_days: int = 7,
    ) -> None:
        self._repository = repository
        self._refresh_days = refresh_days

    async def _ensure_recalc(self, tenant_id: uuid.UUID) -> None:
        latest = await self._repository.latest_generated_at(tenant_id)
        now = datetime.now(UTC)
        stale = latest is None or (now - latest) >= timedelta(days=self._refresh_days)
        if stale:
            rows = await self._repository.build_quality_rows(tenant_id)
            scored = [_score_row(q) for q in rows]
            await self._repository.upsert_quality(tenant_id, scored)

    async def recalculate(self, tenant_id: uuid.UUID, *, force: bool = True) -> int:
        """Re-score the tenant's data quality; returns the number of rows scored.

        ``force=True`` always rebuilds regardless of the 7-day TTL — the ops
        hook for the weekly recalc cron. ``force=False`` falls back to the lazy
        ``_ensure_recalc`` TTL so read paths keep their behavior unchanged.
        """
        if not force:
            await self._ensure_recalc(tenant_id)
            return len(await self._repository.list_quality(tenant_id))
        rows = await self._repository.build_quality_rows(tenant_id)
        scored = [_score_row(q) for q in rows]
        await self._repository.upsert_quality(tenant_id, scored)
        return len(scored)

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        """Timestamp of the current stored run (drives the panel's 'as of')."""
        return await self._repository.latest_generated_at(tenant_id)

    async def org_kpi(self, tenant_id: uuid.UUID) -> QualityOrgKpi:
        await self._ensure_recalc(tenant_id)
        rows = await self._repository.list_quality(tenant_id)
        return self._build_kpi(rows)

    async def employee_quality(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> EmployeeQuality | None:
        """L2 drill-down for a single employee (or None if no run covers them)."""
        await self._ensure_recalc(tenant_id)
        rows = await self._repository.list_quality(tenant_id, employee_id=employee_id)
        return rows[0] if rows else None

    async def list_scores(
        self, tenant_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[EmployeeQuality]:
        """L2 pageable drill-down (worst first), for the admin quality panel."""
        await self._ensure_recalc(tenant_id)
        rows = await self._repository.list_quality(tenant_id)
        rows.sort(key=lambda r: r.score)
        return rows[offset : offset + limit]

    @staticmethod
    def _build_kpi(rows: Sequence[EmployeeQuality]) -> QualityOrgKpi:
        total = len(rows)
        if total == 0:
            return QualityOrgKpi(
                total_scored=0,
                average_score=0.0,
                grade_distribution={},
                department_averages=[],
                generated_at=datetime.now(UTC),
                narrative="No employees with quality scores yet.",
            )
        avg = round(sum(r.score for r in rows) / total, 4)
        by_grade: dict[str, int] = defaultdict(int)
        dept: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for r in rows:
            by_grade[r.grade] += 1
            dept[r.department_name or "Unassigned"].append((r.score, r.grade))
        department_averages = [
            DepartmentQuality(
                department_name=name,
                average_score=round(sum(s for s, _ in scores) / len(scores), 4),
                low_quality_count=sum(1 for _, g in scores if g in ("C", "D", "F")),
                scored=len(scores),
            )
            for name, scores in sorted(
                dept.items(), key=lambda kv: sum(s for s, _ in kv[1]) / len(kv[1])
            )
        ]
        narrative = (
            f"Average data-quality score is {avg} across {total} scored employee(s): "
            f"{by_grade.get('A', 0)} A, {by_grade.get('B', 0)} B, "
            f"{by_grade.get('C', 0)} C, {by_grade.get('D', 0)} D, {by_grade.get('F', 0)} F."
        )
        if department_averages:
            worst = department_averages[0]
            narrative += (
                f" Lowest-quality team is {worst.department_name} (avg {worst.average_score})."
            )
        return QualityOrgKpi(
            total_scored=total,
            average_score=avg,
            grade_distribution=dict(by_grade),
            department_averages=department_averages,
            generated_at=rows[0].generated_at,
            narrative=narrative,
        )


__all__ = [
    "AiHrQualityRepositoryPort",
    "DepartmentQuality",
    "EmployeeQuality",
    "QualityOrgKpi",
    "QualityService",
]
