"""User schemas — re-exports for backward-compatible imports."""

from {name}.schemas.user.requests import ChangePasswordRequest, UserUpdateRequest
from {name}.schemas.user.responses import UserListResponse, UserResponse

__all__ = [
    "ChangePasswordRequest",
    "UserListResponse",
    "UserResponse",
    "UserUpdateRequest",
]
