"""SSO endpoints — SAML/OIDC identity provider callbacks."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from identity.api.deps import get_sso_service
from identity.application.sso.service.sso import SSOService
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/sso", tags=["sso"])


@router.post("/oidc/start")
async def start_oidc(
    provider: str,
    redirect_uri: str,
    sso_svc: SSOService = Depends(get_sso_service),
) -> ResponseEnvelope[dict]:
    """Start OIDC SSO flow — returns authorization URL."""
    result = await sso_svc.start_oidc_flow(provider, redirect_uri)
    return ResponseEnvelope(data=result)


@router.post("/oidc/callback")
async def oidc_callback(
    code: str,
    state: str,
    sso_svc: SSOService = Depends(get_sso_service),
) -> ResponseEnvelope[dict]:
    """Handle OIDC callback — exchange code for tokens, return session."""
    result = await sso_svc.handle_oidc_callback(code, state)
    return ResponseEnvelope(data=result, message="SSO login successful")


@router.post("/saml/start")
async def start_saml(
    provider: str,
    sso_svc: SSOService = Depends(get_sso_service),
) -> ResponseEnvelope[dict]:
    """Start SAML SSO flow."""
    result = await sso_svc.start_saml_flow(provider)
    return ResponseEnvelope(data=result)


@router.post("/saml/callback")
async def saml_callback(
    saml_response: str,
    sso_svc: SSOService = Depends(get_sso_service),
) -> ResponseEnvelope[dict]:
    """Handle SAML callback."""
    result = await sso_svc.handle_saml_callback(saml_response)
    return ResponseEnvelope(data=result, message="SAML SSO login successful")
