"""Wave-2 agent API schemas - Sales Coach + Audit Guardian (SKY-90).

Response models deliberately omit the coach suggestion ``evidence`` payload:
CRM-record evidence stays inside the service and is never rendered by the
manager review UI (same posture as the supervisor delegate). Guardian report
events DO carry evidence because the weekly report page must render evidence
links for operator investigation.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

SuggestionStatus = Literal["pending", "viewed", "accepted", "dismissed"]
ReviewDecision = Literal["accepted", "dismissed"]
ReportStatus = Literal["generated", "reviewed", "archived"]
Severity = Literal["info", "low", "medium", "high", "critical"]


class CoachingSuggestionItem(BaseModel):
    """One coaching suggestion as the manager review UI sees it."""

    id: uuid.UUID
    rep_user_id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    suggestion_type: str
    title: str
    body: str
    status: SuggestionStatus
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CoachingSuggestionListResponse(BaseModel):
    data: list[CoachingSuggestionItem]
    meta: dict[str, Any]


class SuggestionReviewRequest(BaseModel):
    status: ReviewDecision


class GuardianReportItem(BaseModel):
    """Slim weekly report row (no flagged events attached)."""

    id: uuid.UUID
    report_week_start: date
    report_week_end: date
    summary: str
    total_events_scanned: int
    flagged_count: int
    status: ReportStatus
    generated_at: datetime


class GuardianReportListResponse(BaseModel):
    data: list[GuardianReportItem]
    meta: dict[str, Any]


class GuardianEventItem(BaseModel):
    """One flagged event; evidence is rendered as links by the report page."""

    id: uuid.UUID
    source_table: str
    source_id: uuid.UUID
    event_action: str
    severity: Severity
    reason: str
    evidence: dict[str, Any]
    flagged_at: datetime


class GuardianReportDetailResponse(GuardianReportItem):
    events: list[GuardianEventItem]
