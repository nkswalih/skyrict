"""Tenant-scoped ERP document master ORM model - RLS-protected, composite PK.

The document master is the SKY-87 authority for metadata + latest-version
storage. The polymorphic entity reference (``module_ref``/``entity_type``/
``entity_id``) is deliberately NOT a composite FK: documents outlive and span
entity lifecycles across modules, so a hard reference would over-constrain
them. ``tags`` is the human-confirmed tag set; ``ai_tags`` are the
auto-tagger's proposals awaiting ``tags_confirmed``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class ErpDocumentModel(Base):
    __tablename__ = "erp_documents"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "storage_key",
            name="uq_erp_documents_tenant_storage_key",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_erp_documents_size_non_negative"),
        CheckConstraint(
            "version_count >= 1",
            name="ck_erp_documents_version_count_positive",
        ),
        CheckConstraint(
            "ocr_status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_erp_documents_ocr_status",
        ),
        Index("ix_erp_documents_tenant_ocr", "tenant_id", "ocr_status"),
        Index(
            "ix_erp_documents_tenant_module_entity",
            "tenant_id",
            "module_ref",
            "entity_type",
            "entity_id",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=sa_text("0"))
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_backend: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=sa_text("'local'")
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    module_ref: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(
        JSONB(), nullable=False, default=list, server_default=sa_text("'[]'::jsonb")
    )
    ocr_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=sa_text("'pending'")
    )
    ocr_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_tags: Mapped[list[str] | None] = mapped_column(
        JSONB(), nullable=False, default=list, server_default=sa_text("'[]'::jsonb")
    )
    tags_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    version_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("1"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
