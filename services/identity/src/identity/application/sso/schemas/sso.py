"""SSO (Single Sign-On) request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SSOProviderResponse(BaseModel):
    """SSO provider info returned in API responses."""

    id: str
    name: str
    provider_type: str  # "oidc", "saml"
    issuer_url: str
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}


class SSOInitiateRequest(BaseModel):
    """POST /sso/initiate — start SSO login flow."""

    provider_id: str = Field(..., description="SSO provider ID")
    redirect_uri: str = Field(..., description="Where to redirect after auth")


class SSOCallbackRequest(BaseModel):
    """POST /sso/callback — handle SSO callback."""

    code: str = Field(..., description="Authorization code from IdP")
    state: str = Field(..., description="State parameter for CSRF protection")
    provider_id: str


class SSOLinkAccountRequest(BaseModel):
    """POST /sso/link — link SSO to existing account."""

    provider_id: str
    external_id: str
    email: EmailStr


class SSOConfigurationRequest(BaseModel):
    """POST /organizations/{id}/sso — configure SSO for an organization."""

    name: str = Field(..., min_length=1, max_length=256)
    provider_type: str = Field(..., pattern=r"^(oidc|saml)$")
    issuer_url: str
    client_id: str
    client_secret: str = Field(..., min_length=1)
    redirect_uri: str | None = None
    enabled: bool = True
