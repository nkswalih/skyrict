"""Authentication schemas — re-exports for backward-compatible imports."""

from {name}.schemas.auth.requests import (
    LoginRequest,
    LogoutRequest,
    RegisterRequest,
    TokenRefreshRequest,
)
from {name}.schemas.auth.responses import AuthResponse

__all__ = [
    "AuthResponse",
    "LoginRequest",
    "LogoutRequest",
    "RegisterRequest",
    "TokenRefreshRequest",
]
