"""/ai/coaching endpoints - Sales Coach suggestion queue + manager review (SKY-90).

Authentication happens here (JWT re-verification); authorization happens
upstream at the core monolith proxy (``erp.ai.invoke`` + module keys checked
before forwarding - the mirror of the narrator/supplier-risk posture). The
review action additionally flips the suggestion status ledger row and writes
an audit event so accepted/dismissed decisions are never silently lost.

Security: the response schema deliberately omits the ``evidence`` payload
(CRM-record references); the manager UI decides from the suggestion title and
body alone, and evidence never leaves the repository boundary.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.api.v1.schemas.agent_wave2 import (
    CoachingSuggestionItem,
    CoachingSuggestionListResponse,
    SuggestionReviewRequest,
)
from ai_agent.core.audit_events import (
    AI_COACHING_SUGGESTION_ACCEPTED,
    AI_COACHING_SUGGESTION_DISMISSED,
)
from ai_agent.core.audit_service import AuditService
from ai_agent.db.audit_repository import AiAuditLogRepository
from ai_agent.db.coaching_suggestion_repository import CoachingSuggestionRepository

router = APIRouter(prefix="/ai/coaching", tags=["ai-agent-coaching"])


def _to_item(row: Any) -> CoachingSuggestionItem:
    """Map an ORM suggestion row to the wire schema (evidence excluded)."""
    return CoachingSuggestionItem(
        id=row.id,
        rep_user_id=row.rep_user_id,
        opportunity_id=row.opportunity_id,
        lead_id=row.lead_id,
        suggestion_type=row.suggestion_type,
        title=row.title,
        body=row.body,
        status=row.status,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/suggestions", response_model=CoachingSuggestionListResponse)
async def list_suggestions(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    rep_user_id: uuid.UUID | None = None,
) -> CoachingSuggestionListResponse:
    """List pending coaching suggestions for this tenant.

    Optionally scoped to a single rep with ``rep_user_id`` (the manager
    reviewing one rep's queue) - otherwise the full pending queue.
    """
    repo = CoachingSuggestionRepository(session)
    if rep_user_id is None:
        rows = await repo.list_all_pending(tenant_id=user["tenant_id"])
    else:
        rows = await repo.list_pending_for_rep(
            tenant_id=user["tenant_id"],
            rep_user_id=rep_user_id,
        )
    return CoachingSuggestionListResponse(
        data=[_to_item(row) for row in rows],
        meta={"count": len(rows)},
    )


@router.post("/suggestions/{suggestion_id}/review", response_model=CoachingSuggestionItem)
async def review_suggestion(
    suggestion_id: uuid.UUID,
    body: SuggestionReviewRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CoachingSuggestionItem:
    """Accept or dismiss one coaching suggestion (manager decision).

    The decision is recorded on the row (reviewed_by/reviewed_at) and in the
    audit log (``ai.coaching.suggestion.accepted`` / ``...dismissed``). A
    tenant-scoped 404 is returned for unknown or cross-tenant ids.
    """
    repo = CoachingSuggestionRepository(session)
    row = await repo.get_suggestion(
        tenant_id=user["tenant_id"],
        suggestion_id=suggestion_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suggestion not found",
        )

    action = (
        AI_COACHING_SUGGESTION_ACCEPTED
        if body.status == "accepted"
        else AI_COACHING_SUGGESTION_DISMISSED
    )
    await repo.mark_reviewed(
        tenant_id=user["tenant_id"],
        suggestion_id=suggestion_id,
        status=body.status,
        reviewed_by=user["user_id"],
    )
    await AuditService(AiAuditLogRepository(session)).log(
        action=action,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        input_payload={"suggestion_id": str(suggestion_id), "rep_user_id": str(row.rep_user_id)},
    )

    refreshed = await repo.get_suggestion(
        tenant_id=user["tenant_id"],
        suggestion_id=suggestion_id,
    )
    if refreshed is None:  # pragma: no cover - the row just existed above
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suggestion not found",
        )
    return _to_item(refreshed)
