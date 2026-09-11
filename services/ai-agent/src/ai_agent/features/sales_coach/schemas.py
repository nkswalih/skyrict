"""Pydantic schemas for the Sales Coach feature (SKY-90).

Request/response DTOs for the coaching suggestions API. These are the wire
format — the service layer operates on domain port types, not these schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CoachingSuggestionItem(BaseModel):
    """One coaching suggestion in list/detail responses."""

    id: uuid.UUID
    rep_user_id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    suggestion_type: str
    title: str
    body: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    created_at: datetime


class CoachingSuggestionListResponse(BaseModel):
    """List of coaching suggestions."""

    data: list[CoachingSuggestionItem]
    meta: dict[str, Any] = Field(default_factory=dict)


class CoachingSuggestionDetailResponse(BaseModel):
    """Single coaching suggestion detail."""

    data: CoachingSuggestionItem


class CoachingReviewRequest(BaseModel):
    """Manager review action on a coaching suggestion."""

    action: str = Field(..., pattern="^(accepted|dismissed)$")
    note: str | None = None


class CoachingReviewResponse(BaseModel):
    """Response after a manager review action."""

    data: dict[str, Any]
