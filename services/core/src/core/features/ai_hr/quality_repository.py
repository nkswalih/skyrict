"""Data-quality repository for the HR/Payroll AI slice (HR-AI-002, 8.1.3).

Projects per-employee quality signals from the existing ERP tables, computes the
weighted quality score (mandatory 50% / contact 25% / document 25%) in the
service, and persists/reads ``ai_hr_quality_scores`` rows idempotently per
``(tenant_id, employee_id, generated_at)`` (one scoring run per recalc).

Signal mapping (the ticket's buckets reconciled to real columns — there is no
employee banking/payment table in the ERP schema):

  - mandatory (0.50): missing ``email`` / ``phone`` / ``job_title`` /
    ``department_id``; terminated-but-missing ``termination_date``.
  - contact (0.25): invalid ``email`` / ``phone`` format; no active
    ``erp_compensation`` row (proxy for a broken payment-setup link).
  - document (0.25): a required ``erp_employee_documents`` row is missing,
    expired, or expiring within 30 days.

The L1 org KPI aggregates these per department; the L2 drill-down exposes
per-employee rows and requires ``erp.hr.ai.individual`` at the edge.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.ai_hr.models.employee_document import (
    DocumentType,
    EmployeeDocumentModel,
)
from core.features.ai_hr.models.quality_score import QualityScoreModel
from core.features.hr.models.department import DepartmentModel
from core.features.hr.models.employee import EmployeeModel, EmploymentStatus
from core.features.payroll.models.compensation import CompensationModel

_ACTIVE = (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9()\-\s]{7,}$")

# Document types relevant to "freshness" (identity/legal documents).
_FRESHNESS_DOC_TYPES = (
    DocumentType.WORK_PERMIT,
    DocumentType.VISA,
    DocumentType.NATIONAL_ID,
    DocumentType.PASSPORT,
)
_FRESHNESS_WINDOW_DAYS = 30


@dataclass(frozen=True, slots=True)
class EmployeeQuality:
    """One employee's weighted quality signals + score (as-of a run)."""

    employee_id: uuid.UUID
    department_id: uuid.UUID | None
    mandatory_missing: list[str] = field(default_factory=list)
    contact_issues: list[str] = field(default_factory=list)
    document_issues: list[str] = field(default_factory=list)
    # Computed by the service (weighted, 0..1) and persisted on recalc.
    mandatory_score: float = 0.0
    contact_score: float = 0.0
    document_score: float = 0.0
    score: float = 0.0
    grade: str = "F"
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    employee_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    department_name: str | None = None


class AiHrQualityRepository:
    """Read/write access to quality signals and persisted scores."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- signal projection ----------------------------------------------------

    async def build_quality_rows(self, tenant_id: uuid.UUID) -> list[EmployeeQuality]:
        """Per-active-employee quality signals (buckets only; score is added later)."""
        now = date.today()
        cutoff = now.replace(year=now.year - 1)

        latest_comp = (
            select(
                CompensationModel.employee_id.label("employee_id"),
                CompensationModel.is_active.label("is_active"),
                CompensationModel.effective_from.label("effective_from"),
            )
            .distinct(CompensationModel.employee_id)
            .where(
                CompensationModel.tenant_id == tenant_id,
                CompensationModel.effective_from >= cutoff,
            )
            .order_by(
                CompensationModel.employee_id,
                CompensationModel.effective_from.desc(),
            )
            .subquery()
        )

        docs = (
            select(
                EmployeeDocumentModel.employee_id.label("employee_id"),
                EmployeeDocumentModel.doc_type.label("doc_type"),
                EmployeeDocumentModel.expiry_date.label("expiry_date"),
                EmployeeDocumentModel.is_required.label("is_required"),
                EmployeeDocumentModel.status.label("status"),
            )
            .where(EmployeeDocumentModel.tenant_id == tenant_id)
            .subquery()
        )

        stmt = (
            select(
                EmployeeModel.id.label("employee_id"),
                EmployeeModel.department_id.label("department_id"),
                EmployeeModel.email.label("email"),
                EmployeeModel.phone.label("phone"),
                EmployeeModel.job_title.label("job_title"),
                EmployeeModel.employment_status.label("employment_status"),
                EmployeeModel.termination_date.label("termination_date"),
                latest_comp.c.is_active.label("has_active_comp"),
                docs.c.doc_type.label("doc_type"),
                docs.c.expiry_date.label("doc_expiry"),
                docs.c.is_required.label("doc_required"),
                docs.c.status.label("doc_status"),
            )
            .outerjoin(latest_comp, latest_comp.c.employee_id == EmployeeModel.id)
            .outerjoin(docs, docs.c.employee_id == EmployeeModel.id)
            .where(
                EmployeeModel.tenant_id == tenant_id,
                EmployeeModel.employment_status.in_(_ACTIVE),
            )
            .order_by(EmployeeModel.id)
        )
        rows = (await self.session.execute(stmt)).all()

        return self._group_into_quality(rows)

    def _group_into_quality(self, rows: Sequence[Any]) -> list[EmployeeQuality]:
        by_employee: dict[uuid.UUID, dict[str, Any]] = {}
        for r in rows:
            bucket = by_employee.setdefault(
                r.employee_id,
                {
                    "department_id": r.department_id,
                    "email": r.email,
                    "phone": r.phone,
                    "job_title": r.job_title,
                    "status": r.employment_status,
                    "termination": r.termination_date,
                    "has_active_comp": r.has_active_comp,
                    "docs": [],
                },
            )
            if r.doc_type is not None:
                bucket["docs"].append(
                    {
                        "doc_type": r.doc_type,
                        "expiry": r.doc_expiry,
                        "required": r.doc_required,
                        "status": r.doc_status,
                    }
                )

        quality_rows: list[EmployeeQuality] = []
        now = date.today()
        for employee_id, b in by_employee.items():
            mandatory: list[str] = []
            contact: list[str] = []

            if not b["email"]:
                mandatory.append("missing_email")
            elif not _EMAIL_RE.match(b["email"]):
                contact.append("invalid_email")

            if not b["phone"]:
                mandatory.append("missing_phone")
            elif not _PHONE_RE.match(b["phone"]):
                contact.append("invalid_phone")

            if not b["job_title"]:
                mandatory.append("missing_job_title")
            if b["department_id"] is None:
                mandatory.append("missing_department")
            if b["status"] == EmploymentStatus.TERMINATED and b["termination"] is None:
                mandatory.append("terminated_without_termination_date")

            if not b["has_active_comp"]:
                contact.append("missing_compensation")

            document_issues = self._document_issues(b["docs"], now)

            quality_rows.append(
                EmployeeQuality(
                    employee_id=employee_id,
                    department_id=b["department_id"],
                    mandatory_missing=mandatory,
                    contact_issues=contact,
                    document_issues=document_issues,
                )
            )
        return quality_rows

    @staticmethod
    def _document_issues(docs: list[dict[str, Any]], now: date) -> list[str]:
        """Required documents missing / expired / expiring soon."""
        issues: list[str] = []
        # Which freshness-relevant required doc types are present?
        present_relevant = {
            d["doc_type"]
            for d in docs
            if d["doc_type"] in _FRESHNESS_DOC_TYPES and d["status"] == "active"
        }
        for expected in _FRESHNESS_DOC_TYPES:
            if expected not in present_relevant:
                issues.append(f"missing_document:{expected.value}")
        for d in docs:
            if d["doc_type"] not in _FRESHNESS_DOC_TYPES:
                continue
            expiry = d["expiry"]
            if d["status"] == "expired" or (expiry is not None and expiry < now):
                issues.append(f"expired_document:{d['doc_type'].value}")
            elif (
                d["status"] == "active"
                and expiry is not None
                and expiry <= now + timedelta(days=_FRESHNESS_WINDOW_DAYS)
            ):
                issues.append(f"expiring_document:{d['doc_type'].value}")
        return sorted(set(issues))

    # -- persistence ----------------------------------------------------------

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        stmt = select(func.max(QualityScoreModel.generated_at)).where(
            QualityScoreModel.tenant_id == tenant_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_quality(self, tenant_id: uuid.UUID, rows: Sequence[EmployeeQuality]) -> None:
        """Insert one run's rows idempotently per (employee, generated_at)."""
        if not rows:
            return
        now = datetime.now(UTC)
        values = [
            {
                "tenant_id": tenant_id,
                "employee_id": q.employee_id,
                "score": q.score,
                "grade": q.grade,
                "mandatory_score": q.mandatory_score,
                "contact_score": q.contact_score,
                "document_score": q.document_score,
                "issues": {
                    "mandatory": q.mandatory_missing,
                    "contact": q.contact_issues,
                    "document": q.document_issues,
                },
                "generated_at": now,
            }
            for q in rows
        ]
        stmt = insert(QualityScoreModel).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ai_hr_quality_scores_employee_run",
            set_={
                "score": stmt.excluded.score,
                "grade": stmt.excluded.grade,
                "mandatory_score": stmt.excluded.mandatory_score,
                "contact_score": stmt.excluded.contact_score,
                "document_score": stmt.excluded.document_score,
                "issues": stmt.excluded.issues,
            },
        )
        await self.session.execute(stmt)

    # -- reads ----------------------------------------------------------------

    async def list_quality(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[EmployeeQuality]:
        dept = DepartmentModel
        stmt = (
            select(
                QualityScoreModel.employee_id,
                QualityScoreModel.score,
                QualityScoreModel.grade,
                QualityScoreModel.mandatory_score,
                QualityScoreModel.contact_score,
                QualityScoreModel.document_score,
                QualityScoreModel.issues,
                QualityScoreModel.generated_at,
                EmployeeModel.department_id,
                EmployeeModel.employee_number,
                EmployeeModel.first_name,
                EmployeeModel.last_name,
                dept.name.label("department_name"),
            )
            .join(
                EmployeeModel,
                and_(
                    EmployeeModel.tenant_id == QualityScoreModel.tenant_id,
                    EmployeeModel.id == QualityScoreModel.employee_id,
                ),
            )
            .outerjoin(
                dept,
                and_(
                    dept.tenant_id == EmployeeModel.tenant_id,
                    dept.id == EmployeeModel.department_id,
                ),
            )
            .where(QualityScoreModel.tenant_id == tenant_id)
            .order_by(QualityScoreModel.score.asc())
        )
        if employee_id is not None:
            stmt = stmt.where(EmployeeModel.id == employee_id)
        rows = (await self.session.execute(stmt)).all()
        return [
            self._row_to_quality(r)
            for r in rows
            if (r.generated_at == (await self._latest_run(tenant_id)))
        ]

    async def _latest_run(self, tenant_id: uuid.UUID) -> datetime | None:
        return await self.latest_generated_at(tenant_id)

    def _row_to_quality(self, r: Any) -> EmployeeQuality:
        issues = cast("dict[str, list[str]]", r.issues or {})
        return EmployeeQuality(
            employee_id=r.employee_id,
            department_id=r.department_id,
            mandatory_missing=issues.get("mandatory", []),
            contact_issues=issues.get("contact", []),
            document_issues=issues.get("document", []),
            score=float(cast("Any", r.score)),
            grade=r.grade,
            generated_at=r.generated_at,
            employee_number=r.employee_number,
            first_name=r.first_name,
            last_name=r.last_name,
            department_name=r.department_name,
        )
