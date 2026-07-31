"""Auth endpoints — login, register, refresh, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from {name}.api.deps import get_current_user
from {name}.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RegisterRequest,
    TokenRefreshRequest,
)
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ResponseEnvelope[AuthResponse])
async def login(
    body: LoginRequest,
    request: Request,
) -> ResponseEnvelope[AuthResponse]:
    """Authenticate a user and return tokens."""
    # TODO: Inject AuthenticationService via deps
    raise NotImplementedError("Inject AuthenticationService via deps")


@router.post("/register", response_model=ResponseEnvelope[AuthResponse])
async def register(
    body: RegisterRequest,
    request: Request,
) -> ResponseEnvelope[AuthResponse]:
    """Register a new user and return tokens."""
    raise NotImplementedError("Inject AuthenticationService via deps")


@router.post("/refresh", response_model=ResponseEnvelope[AuthResponse])
async def refresh_token(
    body: TokenRefreshRequest,
) -> ResponseEnvelope[AuthResponse]:
    """Refresh an access token using a refresh token."""
    raise NotImplementedError("Inject TokenService via deps")


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    current_user: dict = Depends(get_current_user),
) -> ResponseEnvelope[None]:
    """Revoke the current session."""
    raise NotImplementedError("Inject TokenService via deps")


@router.post("/introspect")
async def introspect_token(
    body: TokenRefreshRequest,
) -> ResponseEnvelope[dict]:
    """Introspect a token — return its claims if active."""
    raise NotImplementedError("Inject TokenService via deps")
