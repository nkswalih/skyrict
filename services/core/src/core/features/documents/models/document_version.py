"""Append-only per-version document history ORM model - RLS-protected, composite PK.

``version_number`` starts at 1 and increments per document; the master row's
storage fields always mirror the latest version. The composite FK to
``erp_documents`` includes ``tenant_id`` so referential integrity agrees with
RLS (same convention as ``erp_supplier_performance`` in migration 0038).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class ErpDocumentVersionModel(Base):
    __tablename__ = "erp_document_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["erp_documents.tenant_id", "erp_documents.id"],
            ondelete="CASCADE",
            name="fk_erp_document_versions_document_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "version_number",
            name="uq_erp_document_versions_document_version",
        ),
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_erp_document_versions_size_non_negative",
        ),
        Index(
            "ix_erp_document_versions_tenant_document",
            "tenant_id",
            "document_id",
            "version_number",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=sa_text("0"))
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_backend: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=sa_text("'local'")
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
