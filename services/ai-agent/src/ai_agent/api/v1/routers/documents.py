"""/ai/documents/process - machine-to-machine OCR dispatch (SKY-87).

Core's post-commit document dispatch calls this endpoint after an upload
commits (fire-and-forget). Like the inventory sync route, this is NOT a JWT
flow: the caller is the core monolith authenticated by the shared secret
``AI_DOCUMENT_SYNC_TOKEN`` (which must match core's ``CORE_AI_SYNC_TOKEN``).
The tenant is resolved by the middleware from ``X-Tenant-Slug`` / subdomain
Host into ``TenantContext`` and proxy-forwarded to core for the byte fetch.

Authorization happened upstream in core (the document mutation committed only
after the ``erp.documents.write`` gate); this endpoint only runs the AI
enrichment. A missing/mismatched token is a 401, an unconfigured endpoint is a
503, and a failed step degrades to ``ocr_status='failed'`` which a reindex can
retry - the committed upload never blocks on AI.
"""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_db
from ai_agent.core.config import settings
from ai_agent.core.exceptions import AiUnavailableError, AuthenticationError
from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.document_embedding_repository import DocumentEmbeddingRepository
from ai_agent.features.documents.gateway import HttpDocumentGateway
from ai_agent.features.documents.schemas import (
    DocumentProcessRequest,
    DocumentProcessResponse,
)
from ai_agent.features.documents.service import DocumentOcrService

router = APIRouter(prefix="/ai/documents", tags=["ai-documents"])


def require_document_sync_token(request: Request) -> None:
    """Dependency: the bearer must match AI_DOCUMENT_SYNC_TOKEN exactly.

    Fails closed: an empty/invalid shared secret never processes a document.
    """
    expected = settings.DOCUMENT_SYNC_TOKEN
    if not expected:
        raise AiUnavailableError("Document processing is not configured on this service")
    presented = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not presented or not hmac.compare_digest(presented, expected):
        raise AuthenticationError("Invalid sync token")


def _build_service(
    session: AsyncSession,
    request: Request,
) -> DocumentOcrService:
    llm_router = getattr(request.app.state, "llm_router", None)
    return DocumentOcrService(
        store=DocumentEmbeddingRepository(session),
        gateway=HttpDocumentGateway(),
        llm_router=llm_router,
    )


@router.post("/process", response_model=DocumentProcessResponse)
async def document_process(
    body: DocumentProcessRequest,
    _token: Annotated[None, Depends(require_document_sync_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> DocumentProcessResponse:
    """Run OCR + tagging + embedding for a committed core document.

    Accepted and processed synchronously in this request (core emits this as a
    fire-and-forget background request, so latency is absorbed there). The
    result is written to core's callback AND our mirror row.
    """
    if body.action != "process":
        raise AiUnavailableError(f"Unsupported action: {body.action}")

    tenant_id = uuid.UUID(TenantContext.get())
    tenant_slug = TenantContext.get_tenant_slug() or ""

    service = _build_service(session, request)
    await service.process(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        document_id=body.document_id,
    )
    await session.commit()
    return DocumentProcessResponse(document_id=body.document_id)


__all__ = ["router"]
