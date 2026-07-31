"""Authentication request schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """POST /auth/login"""

    email: EmailStr
    password: str = Field(..., min_length=1)
    tenant_slug: str | None = Field(default=None, description="Tenant slug for multi-tenant login")


class RegisterRequest(BaseModel):
    """POST /auth/register"""

    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=256)
    tenant_slug: str | None = Field(default=None, description="Join existing tenant or create new")


class TokenRefreshRequest(BaseModel):
    """POST /auth/refresh"""

    refresh_token: str


class LogoutRequest(BaseModel):
    """POST /auth/logout"""

    refresh_token: str | None = Field(default=None, description="Specific token to revoke; if omitted, revoke all")
