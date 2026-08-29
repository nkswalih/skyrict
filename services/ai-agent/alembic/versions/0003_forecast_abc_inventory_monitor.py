"""Add forecast, ABC classification, and inventory monitor agent (SKY-68).

Creates:
- ai_forecasts: per-SKU demand forecast cache
- ai_abc_classifications: per-SKU ABC band assignments
- inventory_monitor agent_registry row

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- ai_forecasts (tenant-scoped, composite PK, RLS) ---
    op.create_table(
        "ai_forecasts",
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
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("horizon_weeks", sa.Integer(), nullable=False),
        sa.Column(
            "avg_daily_demand", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("weeks_of_supply", sa.Numeric(8, 2), nullable=True),
        sa.Column("stockout_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["erp_products.tenant_id", "erp_products.id"],
            ondelete="CASCADE",
            name="fk_ai_forecasts_product_tenant",
        ),
        sa.UniqueConstraint(
            "tenant_id", "product_id", "horizon_weeks", name="uq_ai_forecast_product_horizon"
        ),
    )
    op.create_index("idx_ai_forecasts_tenant_product", "ai_forecasts", ["tenant_id", "product_id"])

    # --- ai_abc_classifications (tenant-scoped, composite PK, RLS) ---
    op.create_table(
        "ai_abc_classifications",
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
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("band", sa.String(1), nullable=False, server_default=sa.text("'C'")),
        sa.Column("revenue_share", sa.Numeric(8, 4), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["erp_products.tenant_id", "erp_products.id"],
            ondelete="CASCADE",
            name="fk_ai_abc_product_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "product_id", name="uq_ai_abc_product"),
    )
    op.create_index("idx_ai_abc_tenant_band", "ai_abc_classifications", ["tenant_id", "band"])

    # --- inventory_monitor agent (global, no RLS) ---
    op.execute(
        "INSERT INTO agent_registry (id, name, module, enabled) VALUES "
        "(gen_random_uuid(), 'inventory_monitor', 'ai_agent.features.monitor.agent', true) "
        "ON CONFLICT (name) DO NOTHING"
    )

    # --- RLS policies for new tenant-scoped tables ---
    op.execute("ALTER TABLE ai_forecasts ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ai_forecasts_tenant_isolation ON ai_forecasts "
        "USING (tenant_id = public.current_tenant_id())"
    )
    op.execute("ALTER TABLE ai_abc_classifications ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ai_abc_tenant_isolation ON ai_abc_classifications "
        "USING (tenant_id = public.current_tenant_id())"
    )


def downgrade() -> None:
    op.drop_table("ai_abc_classifications")
    op.drop_table("ai_forecasts")
    op.execute("DELETE FROM agent_registry WHERE name = 'inventory_monitor'")
