"""MFA (Multi-Factor Authentication) request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MFAEnableRequest(BaseModel):
    """POST /mfa/enable — initiate MFA setup."""

    method: str = Field(..., pattern=r"^(totp|sms|email)$", description="MFA method")


class MFAVerifyRequest(BaseModel):
    """POST /mfa/verify — verify an MFA code."""

    code: str = Field(..., min_length=6, max_length=6, description="6-digit MFA code")
    method: str = Field(..., pattern=r"^(totp|sms|email)$")


class MFAResponse(BaseModel):
    """Response after MFA setup."""

    secret: str | None = Field(default=None, description="TOTP secret (shown once)")
    qr_code_url: str | None = Field(default=None, description="otpauth:// URI for QR code")
    backup_codes: list[str] = Field(default_factory=list, description="One-time backup codes")
    method: str
    enabled: bool


class MFAStatusResponse(BaseModel):
    """GET /mfa/status — current MFA state."""

    enabled: bool
    methods: list[str] = Field(default_factory=list, description="Enabled MFA methods")
    backup_codes_remaining: int = 0


class MFADisableRequest(BaseModel):
    """POST /mfa/disable — disable MFA."""

    password: str = Field(..., min_length=1, description="Current password for confirmation")
