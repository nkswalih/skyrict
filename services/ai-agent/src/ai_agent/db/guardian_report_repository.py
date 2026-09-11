"""Database access for Audit Guardian reports and events (SKY-90).

Owns the CRUD concerns for ``ai_guardian_reports`` and ``ai_guardian_events``.
All writes are scoped by ``tenant_id`` so RLS never sees a cross-tenant leak.
The repository is the ONLY file that touches SQLAlchemy (import-linter contract).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from ai_agent.models.ai_guardian_event import AiGuardianEventModel
from ai_agent.models.ai_guardian_report import AiGuardianReportModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class GuardianReportRepository:
    """Tenant-scoped CRUD for guardian reports and events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- reports ------------------------------------------------------------

    async def create_report(
        self,
        *,
        tenant_id: uuid.UUID,
        report_week_start: date,
        report_week_end: date,
        summary: str,
        total_events_scanned: int,
        flagged_count: int,
    ) -> uuid.UUID:
        """Persist one weekly report and return its id."""
        now = datetime.now(UTC)
        row = AiGuardianReportModel(
            tenant_id=tenant_id,
            id=uuid.uuid4(),
            report_week_start=report_week_start,
            report_week_end=report_week_end,
            summary=summary,
            total_events_scanned=total_events_scanned,
            flagged_count=flagged_count,
            status="generated",
            generated_at=now,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row.id

    async def get_report(
        self,
        *,
        tenant_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> AiGuardianReportModel | None:
        stmt = select(AiGuardianReportModel).where(
            AiGuardianReportModel.tenant_id == tenant_id,
            AiGuardianReportModel.id == report_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        *,
        tenant_id: uuid.UUID,
        limit: int = 20,
    ) -> list[AiGuardianReportModel]:
        stmt = (
            select(AiGuardianReportModel)
            .where(AiGuardianReportModel.tenant_id == tenant_id)
            .order_by(AiGuardianReportModel.report_week_start.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_report_reviewed(
        self,
        *,
        tenant_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> None:
        await self._session.execute(
            update(AiGuardianReportModel)
            .where(
                AiGuardianReportModel.tenant_id == tenant_id,
                AiGuardianReportModel.id == report_id,
            )
            .values(status="reviewed")
        )
        await self._session.flush()

    # --- events -------------------------------------------------------------

    async def create_event(
        self,
        *,
        tenant_id: uuid.UUID,
        report_id: uuid.UUID | None,
        source_table: str,
        source_id: uuid.UUID,
        event_action: str,
        severity: str,
        reason: str,
        evidence: dict[str, object],
    ) -> uuid.UUID:
        """Persist one flagged event and return its id."""
        row = AiGuardianEventModel(
            tenant_id=tenant_id,
            id=uuid.uuid4(),
            report_id=report_id,
            source_table=source_table,
            source_id=source_id,
            event_action=event_action,
            severity=severity,
            reason=reason,
            evidence=evidence,
            flagged_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row.id

    async def list_events_for_report(
        self,
        *,
        tenant_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> list[AiGuardianEventModel]:
        stmt = (
            select(AiGuardianEventModel)
            .where(
                AiGuardianEventModel.tenant_id == tenant_id,
                AiGuardianEventModel.report_id == report_id,
            )
            .order_by(AiGuardianEventModel.severity.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
