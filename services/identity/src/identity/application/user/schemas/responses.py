"""User response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserResponse(BaseModel):
    """User data returned in API responses."""

    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Paginated user list."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int
