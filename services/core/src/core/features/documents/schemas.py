"""Documents schemas - the API boundary (requests and responses).

Responses are built from the pure-domain dataclasses via ``from_entity`` so the
HTTP layer never leaks ORM or storage details. ``tags``/``ai_tags`` are plain
lists of strings; OCR status is one of ``pending|processing|ready|failed``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from core.domain.entities import Document, DocumentVersion

# OCR status lifecycle (§5): pending -> processing -> ready | failed.
OCR_STATUSES: tuple[str, ...] = ("pending", "processing", "ready", "failed")

# Allowed modules a document may be linked to (mirrors the entity-link rule in
# core/core/permissions.py); an empty-string module means "general / unlinked".
MODULE_REFS: tuple[str, ...] = (
    "",
    "inventory",
    "sales",
    "crm",
    "finance",
    "hr",
    "payroll",
)


class DocumentLinkCreate(BaseModel):
    """Optional foreign reference to a domain entity (module + polymorphic ref)."""

    module_ref: str = Field(default="", max_length=64)
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: str | None = Field(default=None, max_length=64)


class DocumentUploadIn(BaseModel):
    """Multipart upload meta for POST /documents (file streamed separately)."""

    filename: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., min_length=1, max_length=128)
    module_ref: str = Field(default="", max_length=64)
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: str | None = Field(default=None, max_length=64)
    tags: list[str] = Field(default_factory=list)


class DocumentTagUpdate(BaseModel):
    """PATCH /documents/{id} - partial update of link + tags (not content)."""

    module_ref: str | None = Field(default=None, max_length=64)
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = None
    filename: str | None = Field(default=None, min_length=1, max_length=255)


class TagConfirmIn(BaseModel):
    """POST /documents/{id}/tags/confirm - pin AI-suggested tags as authoritative."""

    ai_tags: list[str] = Field(default_factory=list, max_length=200)


class DocumentVersionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    storage_backend: str
    storage_key: str
    created_by: uuid.UUID | None = None
    created_at: datetime
    download_url: str | None = None

    @classmethod
    def from_entity(
        cls, version: DocumentVersion, *, download_url: str | None = None
    ) -> DocumentVersionResponse:
        assert version.id is not None
        assert version.created_at is not None
        assert version.mime_type is not None
        return cls(
            id=version.id,
            document_id=version.document_id,
            version_number=version.version_number,
            filename=version.filename,
            mime_type=version.mime_type,
            size_bytes=version.size_bytes,
            checksum_sha256=version.checksum_sha256,
            storage_backend=version.storage_backend,
            storage_key=version.storage_key,
            created_by=version.created_by,
            created_at=version.created_at,
            download_url=download_url,
        )


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    storage_backend: str
    storage_key: str
    module_ref: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    ocr_status: str
    ocr_error: str | None = None
    extracted_text: str | None = None
    ai_tags: list[str] = Field(default_factory=list)
    tags_confirmed: bool = False
    version_count: int = 1
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    latest_version: DocumentVersionResponse | None = None

    @classmethod
    def from_entity(
        cls,
        document: Document,
        *,
        latest_version: DocumentVersionResponse | None = None,
    ) -> DocumentResponse:
        assert document.id is not None
        assert document.created_at is not None
        assert document.updated_at is not None
        assert document.mime_type is not None
        return cls(
            id=document.id,
            tenant_id=document.tenant_id,
            filename=document.filename,
            mime_type=document.mime_type,
            size_bytes=document.size_bytes,
            checksum_sha256=document.checksum_sha256,
            storage_backend=document.storage_backend,
            storage_key=document.storage_key,
            module_ref=document.module_ref,
            entity_type=document.entity_type,
            entity_id=document.entity_id,
            tags=list(document.tags or []),
            ocr_status=document.ocr_status,
            ocr_error=document.ocr_error,
            extracted_text=document.extracted_text,
            ai_tags=list(document.ai_tags or []),
            tags_confirmed=document.tags_confirmed,
            version_count=document.version_count,
            created_by=document.created_by,
            created_at=document.created_at,
            updated_at=document.updated_at,
            latest_version=latest_version,
        )


class DocumentOcrResult(BaseModel):
    """POST /documents/{id}/ocr/result - ai-agent OCR callback (m2m only)."""

    ocr_status: str = Field(..., pattern="^(processing|ready|failed)$")
    extracted_text: str | None = None
    ai_tags: list[str] = Field(default_factory=list)
    error_message: str | None = None


class ReindexRequest(BaseModel):
    """POST /documents/reindex - re-enqueue OCR for documents in a state."""

    ocr_status: str = Field(default="failed", pattern="^(failed|ready)$")


class DocumentReindexBatch(BaseModel):
    """The ai-agent-facing ingest pull of documents needing re-processing."""

    document_id: uuid.UUID
    tenant_id: uuid.UUID
    filename: str
    mime_type: str
    storage_backend: str
    storage_key: str
    size_bytes: int
    ocr_status: str


__all__ = [
    "MODULE_REFS",
    "OCR_STATUSES",
    "DocumentLinkCreate",
    "DocumentOcrResult",
    "DocumentReindexBatch",
    "DocumentResponse",
    "DocumentTagUpdate",
    "DocumentUploadIn",
    "DocumentVersionResponse",
    "ReindexRequest",
    "TagConfirmIn",
]
