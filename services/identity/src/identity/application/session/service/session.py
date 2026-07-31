"""Session service — track, list, revoke user sessions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from identity.application.session.models.session import SessionModel
from identity.application.session.repository.session import SessionRepository
from skyrict_common.exceptions import SessionNotFoundError


class SessionService:
    """Manages user sessions — creation, listing, revocation."""

    def __init__(self, session_repo: SessionRepository) -> None:
        self.session_repo = session_repo

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        refresh_token_hash: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> SessionModel:
        """Create a new session record."""
        session = SessionModel(
            user_id=user_id,
            tenant_id=tenant_id,
            refresh_token_hash=refresh_token_hash,
            user_agent=user_agent,
            ip_address=ip_address,
            is_active=True,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        return await self.session_repo.create(session)

    async def list_user_sessions(self, user_id: uuid.UUID) -> list[SessionModel]:
        """List all active sessions for a user."""
        return await self.session_repo.get_active_by_user(user_id)

    async def revoke_session(self, session_id: uuid.UUID) -> None:
        """Revoke a specific session."""
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError()
        await self.session_repo.revoke_session(session_id)

    async def revoke_all_sessions(self, user_id: uuid.UUID) -> None:
        """Revoke all sessions for a user (force logout everywhere)."""
        await self.session_repo.revoke_all_for_user(user_id)
