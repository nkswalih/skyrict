"""Documents feature schemas - API boundary for OCR dispatch (SKY-87).

Request/response models for POST /ai/documents/process. Core fires this
endpoint after a document upload commits; ai-agent pulls the byte stream,
runs OCR + tagging + embedding, then writes results back to core via the
m2m callback (POST /documents/{id}/ocr/result).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import uuid
    from datetime import datetime


class DocumentProcessRequest(BaseModel):
    """Core's OCR dispatch payload - identifies the document to process."""

    action: str = Field(default="process", description="always 'process'")
    document_id: uuid.UUID = Field(..., description="core document UUID to process")


class DocumentProcessResponse(BaseModel):
    """Acknowledgement that the document has been queued for processing."""

    document_id: uuid.UUID
    status: str = Field(default="accepted")
    message: str = "Document queued for OCR processing"


class DocumentOcrCallback(BaseModel):
    """Payload ai-agent sends back to core's POST /documents/{id}/ocr/result."""

    ocr_status: str = Field(
        ...,
        pattern="^(processing|ready|failed)$",
        description="OCR lifecycle status",
    )
    extracted_text: str | None = Field(default=None, description="extracted text content")
    ai_tags: list[str] = Field(
        default_factory=list,
        max_length=200,
        description="AI-suggested tags for the document",
    )
    error_message: str | None = Field(
        default=None,
        description="error details when ocr_status is 'failed'",
    )


class DocumentReindexRequest(BaseModel):
    """CLI reindex request - re-process documents in a given status."""

    ocr_status: str = Field(
        default="failed",
        pattern="^(failed|ready)$",
        description="which documents to re-process",
    )
    limit: int = Field(default=50, ge=1, le=200, description="max documents to reindex")


class DocumentReindexResponse(BaseModel):
    """Summary of a reindex operation."""

    enqueued: int = Field(description="number of documents queued for re-processing")
    status: str = "accepted"


class DocumentEmbeddingRow(BaseModel):
    """Single document embedding row for admin/debug queries."""

    document_id: uuid.UUID
    tenant_id: uuid.UUID
    extracted_text: str | None = None
    ai_tags: list[str] = Field(default_factory=list)
    processing_status: str
    chunk_count: int = 0
    confidence_score: float | None = None
    processed_at: datetime | None = None
    created_at: datetime | None = None


__all__ = [
    "DocumentEmbeddingRow",
    "DocumentOcrCallback",
    "DocumentProcessRequest",
    "DocumentProcessResponse",
    "DocumentReindexRequest",
    "DocumentReindexResponse",
]
