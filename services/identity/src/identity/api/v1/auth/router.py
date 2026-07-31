"""Auth endpoints — login, register, refresh, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from identity.api.deps import get_authn_service, get_current_user, get_token_service
from identity.application.auth.schemas import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RegisterRequest,
    TokenRefreshRequest,
)
from identity.application.auth.service.authentication import AuthenticationService
from identity.application.auth.service.token import TokenService
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ResponseEnvelope[AuthResponse])
async def login(
    body: LoginRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
) -> ResponseEnvelope[AuthResponse]:
    """Authenticate a user and return tokens."""
    result = await authn.login(
        body,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    user = result.pop("user")
    return ResponseEnvelope(
        data=AuthResponse(**result, user=user),
        message="Login successful",
    )


@router.post("/register", response_model=ResponseEnvelope[AuthResponse])
async def register(
    body: RegisterRequest,
    request: Request,
    authn: AuthenticationService = Depends(get_authn_service),
) -> ResponseEnvelope[AuthResponse]:
    """Register a new user and return tokens."""
    result = await authn.register(
        body,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    user = result.pop("user")
    return ResponseEnvelope(
        data=AuthResponse(**result, user=user),
        message="Registration successful",
    )


@router.post("/refresh", response_model=ResponseEnvelope[AuthResponse])
async def refresh_token(
    body: TokenRefreshRequest,
    token_svc: TokenService = Depends(get_token_service),
) -> ResponseEnvelope[AuthResponse]:
    """Refresh an access token using a refresh token."""
    tokens = await token_svc.refresh_tokens(body.refresh_token)
    return ResponseEnvelope(
        data=AuthResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
        ),
        message="Token refreshed",
    )


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    current_user: dict = Depends(get_current_user),
    token_svc: TokenService = Depends(get_token_service),
) -> ResponseEnvelope[None]:
    """Revoke the current session."""
    if body.refresh_token:
        await token_svc.revoke_token(body.refresh_token)
    return ResponseEnvelope(message="Logged out successfully")


@router.post("/introspect")
async def introspect_token(
    body: TokenRefreshRequest,
    token_svc: TokenService = Depends(get_token_service),
) -> ResponseEnvelope[dict]:
    """Introspect a token — return its claims if active."""
    result = await token_svc.introspect(body.refresh_token)
    return ResponseEnvelope(data=result)
