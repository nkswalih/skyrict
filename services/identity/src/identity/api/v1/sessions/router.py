"""Session endpoints — list and revoke active sessions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from identity.api.deps import get_current_user, get_session_service
from identity.application.session.service.session import SessionService
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
    session_svc: SessionService = Depends(get_session_service),
) -> ResponseEnvelope[list[dict]]:
    """List all active sessions for the current user."""
    import uuid

    sessions = await session_svc.list_user_sessions(uuid.UUID(current_user["user_id"]))
    return ResponseEnvelope(
        data=[
            {
                "id": str(s.id),
                "user_agent": s.user_agent,
                "ip_address": s.ip_address,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in sessions
        ]
    )


@router.delete("/{session_id}")
async def revoke_session(
    session_id: UUID,
    current_user: dict = Depends(get_current_user),
    session_svc: SessionService = Depends(get_session_service),
) -> ResponseEnvelope[None]:
    """Revoke a specific session."""
    await session_svc.revoke_session(session_id)
    return ResponseEnvelope(message="Session revoked")


@router.delete("")
async def revoke_all_sessions(
    current_user: dict = Depends(get_current_user),
    session_svc: SessionService = Depends(get_session_service),
) -> ResponseEnvelope[None]:
    """Revoke all sessions for the current user (force logout everywhere)."""
    import uuid

    await session_svc.revoke_all_sessions(uuid.UUID(current_user["user_id"]))
    return ResponseEnvelope(message="All sessions revoked")
