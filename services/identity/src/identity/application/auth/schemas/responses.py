"""Authentication response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from identity.application.user.schemas.responses import UserResponse


class AuthResponse(BaseModel):
    """Response after successful login/register/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(default=1800, description="Access token TTL in seconds")
    user: UserResponse | None = None
