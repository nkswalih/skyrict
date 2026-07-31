"""Tenant request schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    """POST /organizations"""

    name: str = Field(..., min_length=1, max_length=256)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class TenantUpdateRequest(BaseModel):
    """PUT /organizations/{id}"""

    name: str | None = Field(default=None, min_length=1, max_length=256)
    plan: str | None = None
