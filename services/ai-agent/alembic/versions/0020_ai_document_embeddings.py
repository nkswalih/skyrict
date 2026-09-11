"""Add ai_document_embeddings table (SKY-87).

One row per (tenant_id, document_id) holding the extracted text, AI-suggested
tags, embedding vector, and processing status that the document OCR pipeline
produces. Core owns the document metadata (erp_documents); this table owns
the AI enrichment layer (text extraction, tag suggestions, vector embeddings
for semantic search).

Composite PK ``(tenant_id, document_id)`` with a composite FK into core-owned
``erp_documents`` (cross-service idiom identical to ``ai_supplier_risk`` ->
``erp_suppliers``): tenant_id stays the RLS column and integrity is enforced
by the composite FK.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _enable_rls(table: str) -> None:
    """RLS + tenant isolation policy, matching the 0001 convention."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation_{table} ON {table} "
        "USING (tenant_id = public.current_tenant_id())"
    )


def upgrade() -> None:
    op.create_table(
        "ai_document_embeddings",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column("ai_tags", sa.Text, nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column(
            "processing_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("module_ref", sa.String(64), nullable=True),
        sa.Column(
            "chunk_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["erp_documents.tenant_id", "erp_documents.id"],
            ondelete="CASCADE",
            name="fk_ai_doc_emb_document_tenant",
        ),
        sa.Index("idx_ai_doc_emb_tenant_status", "tenant_id", "processing_status"),
        sa.Index("idx_ai_doc_emb_tenant_module", "tenant_id", "module_ref"),
    )
    _enable_rls("ai_document_embeddings")


def downgrade() -> None:
    op.drop_table("ai_document_embeddings")
