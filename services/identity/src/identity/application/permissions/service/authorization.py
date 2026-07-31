"""Authorization service — permission checks, RBAC enforcement."""

from __future__ import annotations

import uuid

from identity.application.auth.repository.user import UserRepository
from skyrict_common.exceptions import AuthorizationError


class AuthorizationService:
    """Handles permission checks and RBAC enforcement."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def check_permission(self, user_id: uuid.UUID, permission: str, *, tenant_id: str) -> bool:
        """Check if a user has a specific permission within their tenant.

        Returns True if authorized, raises AuthorizationError if not.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise AuthorizationError("User not found")

        if not user.is_active:
            raise AuthorizationError("User account is disabled")

        # TODO: Check user's roles -> permissions against the required permission
        # For now, all active users are authorized
        return True

    async def require_permission(self, user_id: uuid.UUID, permission: str, *, tenant_id: str) -> None:
        """Like check_permission but always raises on failure."""
        await self.check_permission(user_id, permission, tenant_id=tenant_id)
