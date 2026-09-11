"""Agent wave 2 tables + registry seeds (SKY-90).

Creates the foundation tables for Sales Coach, Audit Guardian, and memory
compaction:

- ``ai_coaching_suggestions``: per-rep coaching suggestions produced by the
  Sales Coach agent; manager-visible only via role-gated API.
- ``ai_guardian_reports``: weekly integrity reports produced by the Audit
  Guardian agent with evidence links to flagged events.
- ``ai_guardian_events``: individual suspicious events flagged by the Audit
  Guardian, linked to their source audit log entries.
- ``compacted_at`` on ``ai_episodic_memory``: tracks which rows have already
  been compacted into semantic facts (NULL = not yet compacted).

Seeds the ``sales_coach`` and ``audit_guardian`` rows in ``agent_registry``
(enabled, tools empty — the supervisor delegates handle streaming).

Chains after dev's ``0020_ai_document_embeddings`` (SKY-87); both share the
``0019`` parent, so this file was renumbered to ``0021`` on the merge.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- ai_coaching_suggestions (Sales Coach) ----------------------------
    op.create_table(
        "ai_coaching_suggestions",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("rep_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=True), nullable=True),
        sa.Column("suggestion_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'viewed', 'accepted', 'dismissed')",
            name="ck_ai_coaching_suggestions_status",
        ),
        sa.CheckConstraint(
            "suggestion_type IN ('follow_up', 'deal_strategy', 'pipeline_review', 'general')",
            name="ck_ai_coaching_suggestions_type",
        ),
        sa.Index(
            "idx_coaching_suggestions_tenant_status",
            "tenant_id",
            "status",
        ),
        sa.Index(
            "idx_coaching_suggestions_rep",
            "tenant_id",
            "rep_user_id",
        ),
    )

    # --- ai_guardian_reports (Audit Guardian) ------------------------------
    op.create_table(
        "ai_guardian_reports",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("report_week_start", sa.Date(), nullable=False),
        sa.Column("report_week_end", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "total_events_scanned", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("flagged_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'generated'"),
        ),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('generated', 'reviewed', 'archived')",
            name="ck_ai_guardian_reports_status",
        ),
        sa.Index(
            "idx_guardian_reports_tenant_week",
            "tenant_id",
            "report_week_start",
        ),
    )

    # --- ai_guardian_events (flagged suspicious events) --------------------
    op.create_table(
        "ai_guardian_events",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("report_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_table", sa.String(50), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_action", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "flagged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_ai_guardian_events_severity",
        ),
        sa.Index(
            "idx_guardian_events_tenant_severity",
            "tenant_id",
            "severity",
        ),
        sa.Index(
            "idx_guardian_events_report",
            "tenant_id",
            "report_id",
            postgresql_where="report_id IS NOT NULL",
        ),
    )

    # --- compaction column on ai_episodic_memory ---------------------------
    op.add_column(
        "ai_episodic_memory",
        sa.Column(
            "compacted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_episodic_memory_compacted",
        "ai_episodic_memory",
        ["tenant_id", "compacted_at"],
        postgresql_where="compacted_at IS NULL",
    )

    # --- agent_registry seeds -----------------------------------------------
    # sales_coach is a LangGraph module agent (runtime invokes its graph).
    # audit_guardian is a scheduled + supervisor-delegate agent; its module
    # records the owning feature package for operator visibility (it is never
    # invoked through the checkpointed runtime - same convention as the
    # streaming leaves in 0009).
    op.execute(
        "INSERT INTO agent_registry (name, module, graph_id, enabled, tools) VALUES "
        "('sales_coach', 'ai_agent.features.sales_coach.graph', "
        "'sales_coach', true, '[]'::jsonb), "
        "('audit_guardian', 'ai_agent.features.audit_guardian.service', "
        "'audit_guardian', true, '[]'::jsonb) "
        "ON CONFLICT (name) DO NOTHING"
    )


def downgrade() -> None:
    # Remove registry seeds.
    op.execute("DELETE FROM agent_registry WHERE name IN ('sales_coach', 'audit_guardian')")

    # Drop compaction column and index.
    op.drop_index("idx_episodic_memory_compacted", table_name="ai_episodic_memory")
    op.drop_column("ai_episodic_memory", "compacted_at")

    # Drop wave-2 tables (order: FK child first).
    op.drop_table("ai_guardian_events")
    op.drop_table("ai_guardian_reports")
    op.drop_table("ai_coaching_suggestions")
