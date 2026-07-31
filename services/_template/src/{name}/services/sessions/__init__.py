"""Session service package — track, list, revoke user sessions."""

from __future__ import annotations

import uuid


class SessionService:
    """Manages user sessions — creation, listing, revocation."""

    def __init__(self, session_repo) -> None:
        self.session_repo = session_repo

    async def create_session(self, *, user_id: uuid.UUID, tenant_id: uuid.UUID, **kwargs):
        """Create a new session record."""
        raise NotImplementedError

    async def list_user_sessions(self, user_id: uuid.UUID) -> list:
        """List all active sessions for a user."""
        raise NotImplementedError

    async def revoke_session(self, session_id: uuid.UUID) -> None:
        """Revoke a specific session."""
        raise NotImplementedError

    async def revoke_all_sessions(self, user_id: uuid.UUID) -> None:
        """Revoke all sessions for a user."""
        raise NotImplementedError
