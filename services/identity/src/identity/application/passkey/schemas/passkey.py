"""Passkey (WebAuthn) request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PasskeyRegistrationChallengeRequest(BaseModel):
    """POST /passkeys/register/challenge — get a registration challenge."""

    device_name: str = Field(..., min_length=1, max_length=128, description="Friendly device name")


class PasskeyRegistrationVerifyRequest(BaseModel):
    """POST /passkeys/register/verify — complete passkey registration."""

    id: str
    raw_id: str
    type: str = "public-key"
    authenticator_attachment: str | None = None
    client_data_json: str
    attestation_object: str
    transports: list[str] = Field(default_factory=list)


class PasskeyAuthenticationChallengeRequest(BaseModel):
    """POST /passkeys/authenticate/challenge — get an authentication challenge."""

    passkey_id: str | None = Field(default=None, description="Specific passkey to challenge")


class PasskeyAuthenticationVerifyRequest(BaseModel):
    """POST /passkeys/authenticate/verify — complete passkey authentication."""

    id: str
    raw_id: str
    type: str = "public-key"
    client_data_json: str
    authenticator_data: str
    signature: str


class PasskeyResponse(BaseModel):
    """Passkey data returned in API responses."""

    id: str
    name: str
    device_type: str
    created_at: str
    last_used_at: str | None = None
    credential_public_key: str | None = None

    model_config = {"from_attributes": True}


class PasskeyListResponse(BaseModel):
    """List of registered passkeys."""

    passkeys: list[PasskeyResponse]
    total: int
