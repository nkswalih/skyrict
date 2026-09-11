"""/ai/guardian endpoints - Audit Guardian weekly integrity reports (SKY-90).

Authentication happens here (JWT re-verification); authorization happens
upstream at the core monolith proxy (``erp.ai.invoke`` + module keys checked
before forwarding). The weekly report body does not embed flagged events;
clients fetch the detail view to render the report page with evidence links.

Security: events are tenant-scoped (RLS-bound session) and the detail view is
the ONLY place evidence payloads are exposed - they carry user/action/IP
context the operator needs to investigate, never to a chat prompt (the
supervisor delegate still drops evidence entirely).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.api.v1.schemas.agent_wave2 import (
    GuardianEventItem,
    GuardianReportDetailResponse,
    GuardianReportItem,
    GuardianReportListResponse,
)
from ai_agent.db.guardian_report_repository import GuardianReportRepository

router = APIRouter(prefix="/ai/guardian", tags=["ai-agent-guardian"])


def _to_item(row: Any) -> GuardianReportItem:
    return GuardianReportItem(
        id=row.id,
        report_week_start=row.report_week_start,
        report_week_end=row.report_week_end,
        summary=row.summary,
        total_events_scanned=row.total_events_scanned,
        flagged_count=row.flagged_count,
        status=row.status,
        generated_at=row.generated_at,
    )


def _to_event(row: Any) -> GuardianEventItem:
    return GuardianEventItem(
        id=row.id,
        source_table=row.source_table,
        source_id=row.source_id,
        event_action=row.event_action,
        severity=row.severity,
        reason=row.reason,
        evidence=row.evidence,
        flagged_at=row.flagged_at,
    )


@router.get("/reports", response_model=GuardianReportListResponse)
async def list_reports(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
) -> GuardianReportListResponse:
    """List weekly integrity reports, newest week first (default 20)."""
    rows = await GuardianReportRepository(session).list_reports(
        tenant_id=user["tenant_id"],
        limit=limit,
    )
    return GuardianReportListResponse(
        data=[_to_item(row) for row in rows],
        meta={"count": len(rows)},
    )


@router.get("/reports/{report_id}", response_model=GuardianReportDetailResponse)
async def get_report(
    report_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GuardianReportDetailResponse:
    """One weekly report with its flagged events + evidence (report page)."""
    repo = GuardianReportRepository(session)
    report = await repo.get_report(tenant_id=user["tenant_id"], report_id=report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    events = await repo.list_events_for_report(
        tenant_id=user["tenant_id"],
        report_id=report_id,
    )
    return GuardianReportDetailResponse(
        **_to_item(report).model_dump(),
        events=[_to_event(row) for row in events],
    )


@router.post("/reports/{report_id}/review", response_model=GuardianReportItem)
async def review_report(
    report_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GuardianReportItem:
    """Mark one report as reviewed by an operator."""
    repo = GuardianReportRepository(session)
    report = await repo.get_report(tenant_id=user["tenant_id"], report_id=report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    await repo.mark_report_reviewed(tenant_id=user["tenant_id"], report_id=report_id)
    refreshed = await repo.get_report(tenant_id=user["tenant_id"], report_id=report_id)
    if refreshed is None:  # pragma: no cover - the row just existed above
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    return _to_item(refreshed)
