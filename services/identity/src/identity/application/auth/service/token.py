"""Token service — create, refresh, revoke, introspect JWT tokens."""

from __future__ import annotations

import uuid

from identity.core.security import create_access_token, create_refresh_token, verify_jwt
from identity.domain.value_objects import TokenPair
from identity.application.session.repository.session import SessionRepository
from skyrict_common.exceptions import TokenExpiredError, TokenInvalidError


class TokenService:
    """Manages JWT token lifecycle — creation, refresh, revocation."""

    def __init__(self, session_repo: SessionRepository) -> None:
        self.session_repo = session_repo

    async def create_token_pair(self, *, user_id: str, tenant_id: str) -> TokenPair:
        """Create an access + refresh token pair."""
        access_token = create_access_token(user_id, tenant_id=tenant_id)
        refresh_token = create_refresh_token(user_id, tenant_id=tenant_id)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenPair:
        """Validate a refresh token and issue a new pair.

        Raises:
            TokenInvalidError: If the refresh token is invalid.
            TokenExpiredError: If the refresh token has expired.
        """
        payload = verify_jwt(refresh_token)

        if payload.get("type") != "refresh":
            raise TokenInvalidError("Token is not a refresh token")

        user_id = payload["sub"]
        tenant_id = payload["tenant_id"]

        # Verify the session is still active
        sessions = await self.session_repo.get_active_by_user(uuid.UUID(user_id))
        if not sessions:
            raise TokenInvalidError("No active session found")

        # Create new pair
        return await self.create_token_pair(user_id=user_id, tenant_id=tenant_id)

    async def revoke_token(self, refresh_token: str) -> None:
        """Revoke a refresh token (invalidate the session)."""
        payload = verify_jwt(refresh_token)
        if payload.get("type") != "refresh":
            raise TokenInvalidError("Token is not a refresh token")

        await self.session_repo.revoke_all_for_user(uuid.UUID(payload["sub"]))

    async def introspect(self, token: str) -> dict:
        """Introspect a token — return its claims if valid."""
        try:
            payload = verify_jwt(token)
            return {
                "active": True,
                "sub": payload.get("sub"),
                "tenant_id": payload.get("tenant_id"),
                "type": payload.get("type"),
                "exp": payload.get("exp"),
            }
        except (TokenExpiredError, TokenInvalidError):
            return {"active": False}
