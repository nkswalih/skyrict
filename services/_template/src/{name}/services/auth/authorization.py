"""Authorization service — permission checks, RBAC enforcement."""

from __future__ import annotations

import uuid


class AuthorizationService:
    """Handles permission checks and RBAC enforcement."""

    def __init__(self, user_repo) -> None:
        self.user_repo = user_repo

    async def check_permission(self, user_id: uuid.UUID, permission: str, *, tenant_id: str) -> bool:
        """Check if a user has a specific permission within their tenant."""
        raise NotImplementedError

    async def require_permission(self, user_id: uuid.UUID, permission: str, *, tenant_id: str) -> None:
        """Like check_permission but always raises on failure."""
        await self.check_permission(user_id, permission, tenant_id=tenant_id)
