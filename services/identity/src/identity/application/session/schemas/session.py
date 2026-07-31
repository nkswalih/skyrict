"""Session request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SessionResponse(BaseModel):
    """Session data returned in API responses."""

    id: UUID
    user_id: UUID
    tenant_id: UUID
    ip_address: str | None = None
    user_agent: str | None = None
    is_active: bool
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    """Paginated session list."""

    sessions: list[SessionResponse]
    total: int


class SessionRevokeRequest(BaseModel):
    """POST /sessions/{id}/revoke — revoke a specific session."""

    reason: str | None = None


class SessionRevokeAllRequest(BaseModel):
    """POST /sessions/revoke-all — revoke all sessions except current."""

    except_current: bool = True
