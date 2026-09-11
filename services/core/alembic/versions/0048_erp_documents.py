"""Document management platform spine (SKY-87, docs/modules/documents.md).

Core is the document authority: metadata, per-version history, and the blob
storage mapping live here; the ai-agent owns OCR/tagging/embeddings. Two
tenant-scoped, RLS-protected tables:

- ``erp_documents`` - the document master. One row per logical document with
  its latest version's storage mapping, the polymorphic entity reference
  (``module_ref``/``entity_type``/``entity_id`` - the composite-FK convention
  is deliberately NOT used because documents outlive and span entity lifecycles),
  the JSONB tag set, and the OCR lifecycle (``pending -> processing ->
  ready | failed``). ``extracted_text`` returns from the ai-agent callback and
  is stored here so re-embedding/reindexing never needs the blob again.
- ``erp_document_versions`` - one row per uploaded version of a document
  (append-only history; the master row's storage fields always mirror the
  latest version). Version numbers start at 1 and increment per document.

Permissions seeded (mirroring identity's catalog, migration 0024):
``erp.documents.read`` gates the library + semantic search proxy + m2m corpus
pulls; ``erp.documents.write`` gates uploads/version updates/tag edits;
``erp.documents.delete`` gates hard deletes. Entity-linked documents
additionally require the owning module's read key (enforced at the service
edge, not in SQL).

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

_TENANT_SCOPED_TABLES = ("erp_documents", "erp_document_versions")

_OCR_STATUSES = ("pending", "processing", "ready", "failed")

_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("erp.documents.read", "View documents and their extracted content"),
    ("erp.documents.write", "Upload, update, and merge documents"),
    ("erp.documents.delete", "Hard-delete document versions and metadata"),
)


def upgrade() -> None:
    op.create_table(
        "erp_documents",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column(
            "storage_backend", sa.String(32), nullable=False, server_default=sa.text("'local'")
        ),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("module_ref", sa.String(32), nullable=True),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column(
            "tags",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "ocr_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("ocr_error", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "ai_tags",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "tags_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("version_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "storage_key",
            name="uq_erp_documents_tenant_storage_key",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_erp_documents_size_non_negative"),
        sa.CheckConstraint(
            "version_count >= 1",
            name="ck_erp_documents_version_count_positive",
        ),
        sa.CheckConstraint(
            "ocr_status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_erp_documents_ocr_status",
        ),
    )

    op.create_table(
        "erp_document_versions",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column(
            "storage_backend", sa.String(32), nullable=False, server_default=sa.text("'local'")
        ),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["erp_documents.tenant_id", "erp_documents.id"],
            ondelete="CASCADE",
            name="fk_erp_document_versions_document_tenant",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "version_number",
            name="uq_erp_document_versions_document_version",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_erp_document_versions_size_non_negative",
        ),
    )

    op.create_index(
        "ix_erp_documents_tenant_ocr",
        "erp_documents",
        ["tenant_id", "ocr_status"],
    )
    op.create_index(
        "ix_erp_documents_tenant_module_entity",
        "erp_documents",
        ["tenant_id", "module_ref", "entity_type", "entity_id"],
    )
    op.execute("CREATE INDEX ix_erp_documents_tenant_tags ON public.erp_documents USING GIN (tags)")
    op.create_index(
        "ix_erp_document_versions_tenant_document",
        "erp_document_versions",
        ["tenant_id", "document_id", "version_number"],
    )

    # --- Row-Level Security policies ---
    for table in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON public.{table} "
            "USING (tenant_id = public.current_tenant_id()) "
            "WITH CHECK (tenant_id = public.current_tenant_id())"
        )

    for key, description in _PERMISSIONS:
        op.execute(
            "INSERT INTO core_permissions (key, description) VALUES "
            f"('{key}', '{description}') ON CONFLICT (key) DO NOTHING"  # nosec B608
        )


def downgrade() -> None:
    for key, _ in _PERMISSIONS:
        op.execute(f"DELETE FROM core_permissions WHERE key = '{key}'")  # nosec B608

    for table in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON public.{table}")

    for index in (
        "ix_erp_document_versions_tenant_document",
        "ix_erp_documents_tenant_module_entity",
        "ix_erp_documents_tenant_ocr",
    ):
        op.execute(f"DROP INDEX IF EXISTS public.{index}")  # nosec B608
    op.execute("DROP INDEX IF EXISTS public.ix_erp_documents_tenant_tags")  # nosec B608

    op.drop_table("erp_document_versions")
    op.drop_table("erp_documents")
