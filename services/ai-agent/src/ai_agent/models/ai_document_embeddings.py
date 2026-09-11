"""ai_document_embeddings - per-tenant document OCR + embedding store (SKY-87).

One row per (tenant_id, document_id) holding the extracted text, AI-suggested
tags, embedding vector, and processing status that the document OCR pipeline
produces. Core owns the document metadata (erp_documents); this table owns
the AI enrichment layer (text extraction, tag suggestions, vector embeddings
for semantic search).

Composite PK ``(tenant_id, document_id)`` with a composite FK into core-owned
``erp_documents`` (cross-service idiom - that table is owned by core in the
same shared database). ``embedding`` is a 768-dim pgvector column for
semantic similarity search.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiDocumentEmbeddingModel(Base):
    __tablename__ = "ai_document_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["erp_documents.tenant_id", "erp_documents.id"],
            ondelete="CASCADE",
            name="fk_ai_doc_emb_document_tenant",
        ),
        Index("idx_ai_doc_emb_tenant_status", "tenant_id", "processing_status"),
        Index("idx_ai_doc_emb_tenant_module", "tenant_id", "module_ref"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[object | None] = mapped_column(Vector(768), nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    module_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["AiDocumentEmbeddingModel"]
