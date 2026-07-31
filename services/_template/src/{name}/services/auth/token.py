"""Token service — create, refresh, revoke JWT tokens."""

from __future__ import annotations


class TokenService:
    """Manages JWT token lifecycle — creation, refresh, revocation."""

    def __init__(self, session_repo) -> None:
        self.session_repo = session_repo

    async def create_token_pair(self, *, user_id: str, tenant_id: str):
        """Create an access + refresh token pair."""
        raise NotImplementedError

    async def refresh_tokens(self, refresh_token: str):
        """Validate a refresh token and issue a new pair."""
        raise NotImplementedError

    async def revoke_token(self, refresh_token: str) -> None:
        """Revoke a refresh token (invalidate the session)."""
        raise NotImplementedError

    async def introspect(self, token: str) -> dict:
        """Introspect a token — return its claims if valid."""
        raise NotImplementedError
