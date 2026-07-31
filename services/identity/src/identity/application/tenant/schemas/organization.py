"""Organization (Tenant) request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OrganizationCreateRequest(BaseModel):
    """POST /organizations — create a new organization."""

    name: str = Field(..., min_length=1, max_length=256)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    plan: str = Field(default="free", description="Subscription plan")


class OrganizationUpdateRequest(BaseModel):
    """PUT /organizations/{id} — update organization settings."""

    name: str | None = Field(default=None, min_length=1, max_length=256)
    plan: str | None = None
    settings: dict | None = None


class OrganizationResponse(BaseModel):
    """Organization data returned in API responses."""

    id: UUID
    name: str
    slug: str
    plan: str
    is_active: bool
    settings: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrganizationMemberResponse(BaseModel):
    """Organization member data."""

    user_id: UUID
    email: str
    full_name: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class OrganizationMemberInviteRequest(BaseModel):
    """POST /organizations/{id}/members — invite a member."""

    email: str = Field(..., description="Email address to invite")
    role: str = Field(default="member", pattern=r"^(owner|admin|member|viewer)$")


class OrganizationMemberUpdateRequest(BaseModel):
    """PUT /organizations/{id}/members/{user_id} — update member role."""

    role: str = Field(..., pattern=r"^(owner|admin|member|viewer)$")
