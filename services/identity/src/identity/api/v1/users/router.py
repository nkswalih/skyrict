"""User endpoints — profile, update, password change."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from identity.api.deps import get_current_user, get_user_repo
from identity.application.auth.repository.user import UserRepository
from identity.application.user.schemas import ChangePasswordRequest, UserResponse, UserUpdateRequest
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ResponseEnvelope[UserResponse])
async def get_my_profile(
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
) -> ResponseEnvelope[UserResponse]:
    """Get the current user's profile."""
    user = await user_repo.get_by_id(current_user["user_id"])
    return ResponseEnvelope(data=UserResponse.model_validate(user))


@router.put("/me", response_model=ResponseEnvelope[UserResponse])
async def update_my_profile(
    body: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
) -> ResponseEnvelope[UserResponse]:
    """Update the current user's profile."""
    user = await user_repo.get_by_id(current_user["user_id"])
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.email is not None:
        user.email = body.email
    await user_repo.commit()
    return ResponseEnvelope(data=UserResponse.model_validate(user), message="Profile updated")


@router.post("/me/password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
) -> ResponseEnvelope[None]:
    """Change the current user's password."""
    from identity.core.security import hash_password, verify_password

    user = await user_repo.get_by_id(current_user["user_id"])
    if not verify_password(body.current_password, user.hashed_password):
        from skyrict_common.exceptions import InvalidPasswordError
        raise InvalidPasswordError("Current password is incorrect")

    user.hashed_password = hash_password(body.new_password)
    await user_repo.commit()
    return ResponseEnvelope(message="Password changed successfully")
