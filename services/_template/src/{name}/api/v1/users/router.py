"""User endpoints — profile, update, password change."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from {name}.api.deps import get_current_user
from {name}.schemas.user import ChangePasswordRequest, UserResponse, UserUpdateRequest
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ResponseEnvelope[UserResponse])
async def get_my_profile(
    current_user: dict = Depends(get_current_user),
) -> ResponseEnvelope[UserResponse]:
    """Get the current user's profile."""
    raise NotImplementedError("Inject UserRepository via deps")


@router.put("/me", response_model=ResponseEnvelope[UserResponse])
async def update_my_profile(
    body: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> ResponseEnvelope[UserResponse]:
    """Update the current user's profile."""
    raise NotImplementedError("Inject UserRepository via deps")


@router.post("/me/password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
) -> ResponseEnvelope[None]:
    """Change the current user's password."""
    raise NotImplementedError("Inject UserRepository via deps")
