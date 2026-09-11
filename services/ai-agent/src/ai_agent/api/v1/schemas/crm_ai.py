"""Request/response schemas for CRM AI endpoints (SKY-61 Part 11/12).

Badge views return the *latest* score/health plus the deterministic factor
breakdown the UI renders in a tooltip on hover. Health bands are the
``green|yellow|red`` strings from ai_deal_health; scores are 0-100 ints.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class HealthBand(StrEnum):
    """Deal health bands (matches the ai_deal_health CHECK constraint)."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class FollowUpSuggestionType(StrEnum):
    """Follow-up suggestion types (matches the CHECK constraint)."""

    EMAIL = "email"
    CALL = "call"
    MEETING = "meeting"
    TASK = "task"


class LeadScoreResponse(BaseModel):
    """Latest deterministic AI score for a lead (GET /ai/crm/leads/{id}/score)."""

    lead_id: uuid.UUID
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    factors: list[str]
    model_version: str
    computed_at: datetime


class DealHealthResponse(BaseModel):
    """Latest AI health assessment for an opportunity."""

    opportunity_id: uuid.UUID
    health: HealthBand
    confidence: float = Field(ge=0, le=1)
    risk_factors: list[str]
    recommended_actions: list[str]
    engagement_velocity: float | None = None
    days_in_stage: int | None = None
    computed_at: datetime


class DealHealthSweepResponse(BaseModel):
    """Band counts from a bulk sweep (POST /ai/crm/opportunities/sweep)."""

    assessed: int = Field(ge=0)
    healthy: int = Field(ge=0)
    at_risk: int = Field(ge=0)
    critical: int = Field(ge=0)


class FollowUpItem(BaseModel):
    """One follow-up suggestion for a user (GET /ai/crm/follow-ups)."""

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    suggestion_type: FollowUpSuggestionType
    draft_content: str
    reasoning: str
    confidence: float = Field(ge=0, le=1)
    status: str
    created_at: datetime
    expires_at: datetime
