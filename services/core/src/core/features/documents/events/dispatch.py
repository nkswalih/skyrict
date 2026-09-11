"""Document events + OCR dispatch hooks (SKY-87).

Two concerns ride on every document mutation:

1. Domain events: ``docs/modules/documents.md`` topics envelope through the
   process-wide producer (Phase 1 = structlog stub). The documents service
   calls these AFTER the mutation transaction commits, so a rolled-back write
   can never emit a phantom event (same rule as inventory).

2. Post-commit OCR dispatch: the upload/version-add production ALSO forwards
   the document key to ai-agent's ``POST /api/v1/ai/documents/process`` so the
   OCR pipeline can pull the byte stream via the storage key. Dispatch is
   BEST-EFFORT: it runs as a background task on the request loop and a failure
   is logged, never turned into a 500 - the write already committed. Recovery
   is ``POST /api/v1/documents/reindex`` (core) / ``ai-agent documents reindex``.
   Disabled when ``CORE_AI_SYNC_TOKEN`` (or the routed tenant slug) is absent.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import structlog

from core.core.config import settings
from core.core.tenant_context import TenantContext
from core.events.constants import (
    DOCUMENT_DELETED,
    DOCUMENT_DOWNLOADED,
    DOCUMENT_TAGS_CONFIRMED,
    DOCUMENT_UPLOADED,
    DOCUMENT_VERSION_ADDED,
)
from core.events.producers import get_event_producer
from skyrict_events.base import BaseEvent

logger = structlog.get_logger("core.events.documents")

_OCR_PATH = "/api/v1/ai/documents/process"


class DocumentUploadedEvent(BaseEvent):
    """Envelope for ``documents.document.uploaded`` (new document, v1)."""

    event_type: str = DOCUMENT_UPLOADED


class DocumentVersionAddedEvent(BaseEvent):
    """Envelope for ``documents.document.version_added`` (version appended)."""

    event_type: str = DOCUMENT_VERSION_ADDED


class DocumentDeletedEvent(BaseEvent):
    """Envelope for ``documents.document.deleted`` (hard delete)."""

    event_type: str = DOCUMENT_DELETED


class DocumentDownloadedEvent(BaseEvent):
    """Envelope for ``documents.document.downloaded`` (stream requested)."""

    event_type: str = DOCUMENT_DOWNLOADED


class DocumentTagsConfirmedEvent(BaseEvent):
    """Envelope for ``documents.document.tags_confirmed`` (human pinned tags)."""

    event_type: str = DOCUMENT_TAGS_CONFIRMED


def publish_document_uploaded(*, tenant_id: str | uuid.UUID, document_id: str | uuid.UUID) -> None:
    """Notify subscribers of a new document + dispatch OCR to ai-agent."""
    event = DocumentUploadedEvent(
        tenant_id=str(tenant_id),
        metadata={"document_id": str(document_id)},
    )
    get_event_producer().publish(DOCUMENT_UPLOADED, event, key=str(tenant_id))
    _spawn_ocr_dispatch({"action": "process", "document_id": str(document_id)})


def publish_document_version_added(
    *, tenant_id: str | uuid.UUID, document_id: str | uuid.UUID
) -> None:
    event = DocumentVersionAddedEvent(
        tenant_id=str(tenant_id),
        metadata={"document_id": str(document_id)},
    )
    get_event_producer().publish(DOCUMENT_VERSION_ADDED, event, key=str(tenant_id))
    _spawn_ocr_dispatch({"action": "process", "document_id": str(document_id)})


def publish_document_deleted(*, tenant_id: str | uuid.UUID, document_id: str | uuid.UUID) -> None:
    event = DocumentDeletedEvent(
        tenant_id=str(tenant_id),
        metadata={"document_id": str(document_id)},
    )
    get_event_producer().publish(DOCUMENT_DELETED, event, key=str(tenant_id))


def publish_document_downloaded(
    *, tenant_id: str | uuid.UUID, document_id: str | uuid.UUID
) -> None:
    event = DocumentDownloadedEvent(
        tenant_id=str(tenant_id),
        metadata={"document_id": str(document_id)},
    )
    get_event_producer().publish(DOCUMENT_DOWNLOADED, event, key=str(tenant_id))


def publish_document_tags_confirmed(
    *, tenant_id: str | uuid.UUID, document_id: str | uuid.UUID, tags: list[str]
) -> None:
    event = DocumentTagsConfirmedEvent(
        tenant_id=str(tenant_id),
        metadata={"document_id": str(document_id), "tags": tags},
    )
    get_event_producer().publish(DOCUMENT_TAGS_CONFIRMED, event, key=str(tenant_id))


def reindex_failed(*, tenant_id: str | uuid.UUID, document_id: str | uuid.UUID) -> None:
    """Re-enqueue a single failed/ready document for processing (admin reindex)."""
    _spawn_ocr_dispatch({"action": "process", "document_id": str(document_id)})


# ---------------------------------------------------------------------------
# Best-effort OCR dispatch
# ---------------------------------------------------------------------------


def _spawn_ocr_dispatch(payload: dict[str, Any]) -> None:
    """POST *payload* to ai-agent as a fire-and-forget background task.

    ai-agent resolves the tenant from the forwarded slug, never from the
    payload. Skips when sync is disabled (empty token) or no tenant slug is
    routable (e.g. an emit outside an authenticated request).
    """
    token = settings.AI_SYNC_TOKEN
    slug = TenantContext.get_tenant_slug()
    if not token or not slug:
        logger.debug(
            "documents.ocr.sync_skipped",
            reason="sync token or tenant slug unavailable",
            tenant_id=TenantContext.get_optional(),
        )
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("documents.ocr.sync_skipped", reason="no running loop")
        return
    task = loop.create_task(_post_dispatch(payload=payload, token=token, tenant_slug=slug))
    task.add_done_callback(_log_dispatch_failure)


def _log_dispatch_failure(task: asyncio.Task[object]) -> None:
    """Log (never raise) a failed hand-off - the write already committed."""
    try:
        task.result()
    except Exception:
        logger.exception(
            "documents.ocr.sync_failed",
            message="document ocr dispatch failed; document stays pending for reindex",
        )


async def _post_dispatch(*, payload: dict[str, Any], token: str, tenant_slug: str) -> None:
    """POST one dispatdh payload to ai-agent; httpx errors surface to the caller."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Slug": tenant_slug,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=settings.AI_AGENT_TIMEOUT_SECONDS) as client:
        await client.post(
            f"{settings.AI_AGENT_URL.rstrip('/')}{_OCR_PATH}",
            headers=headers,
            json=payload,
        )


__all__ = [
    "DocumentDeletedEvent",
    "DocumentDownloadedEvent",
    "DocumentTagsConfirmedEvent",
    "DocumentUploadedEvent",
    "DocumentVersionAddedEvent",
    "publish_document_deleted",
    "publish_document_downloaded",
    "publish_document_tags_confirmed",
    "publish_document_uploaded",
    "publish_document_version_added",
    "reindex_failed",
]
