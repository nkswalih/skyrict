"""User request schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserUpdateRequest(BaseModel):
    """PUT /users/me"""

    full_name: str | None = Field(default=None, min_length=1, max_length=256)
    email: EmailStr | None = None


class ChangePasswordRequest(BaseModel):
    """POST /users/me/password"""

    current_password: str
    new_password: str = Field(..., min_length=8)
