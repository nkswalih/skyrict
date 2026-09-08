"""ai_l3_narrative_snapshots - cached L3 HR/Payroll AI narratives (HR-AI-003).

One row per narrated L3 analytics output. ``kind`` distinguishes the three
features sharing the table - ``payroll_cost``, ``leave_pay_correlation``,
``compliance_digest`` - so a single snapshot store backs all three. ``status``
is ``generated`` when a narrative was produced or ``abstained`` when the
narrator deliberately declined (thin data, stale source, LLM disabled); the
``caveat`` carries the reason. ``figures`` stores the verified token->amount
gold-signal map the narrative cites (placeholder substitution source), so
rendered digits always come from the reconciliation-tested payload, never from
model prose. ``as_of`` is the business period the narrative covers.

Rows are insert-per-generation; cache semantics are derived (repository picks
the newest row for a (kind, as_of) pair), mirroring ai_digest_snapshots (0007)
and 0001/0012 RLS conventions. Aggregates only - no employee-level data.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _enable_rls(table: str) -> None:
    """Enable RLS and the tenant-isolation policy (0001/0012 convention)."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation_{table} ON {table} "
        "USING (tenant_id = public.current_tenant_id()) "
        "WITH CHECK (tenant_id = public.current_tenant_id())"
    )


def upgrade() -> None:
    op.create_table(
        "ai_l3_narrative_snapshots",
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
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.String(32), primary_key=True, nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'generated'"),
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("points", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("caveat", sa.Text(), nullable=True),
        sa.Column("figures", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_ai_l3_narratives_tenant_kind_as_of",
        "ai_l3_narrative_snapshots",
        ["tenant_id", "kind", "as_of"],
    )
    _enable_rls("ai_l3_narrative_snapshots")


def downgrade() -> None:
    op.execute("ALTER TABLE ai_l3_narrative_snapshots DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_ai_l3_narrative_snapshots "
        "ON ai_l3_narrative_snapshots"
    )
    op.drop_index(
        "idx_ai_l3_narratives_tenant_kind_as_of",
        table_name="ai_l3_narrative_snapshots",
    )
    op.drop_table("ai_l3_narrative_snapshots")