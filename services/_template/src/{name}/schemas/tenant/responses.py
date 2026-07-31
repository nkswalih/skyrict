"""Tenant response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TenantResponse(BaseModel):
    """Tenant data returned in API responses."""

    id: UUID
    name: str
    slug: str
    is_active: bool
    plan: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
