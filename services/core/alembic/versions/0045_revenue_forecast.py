"""Revenue forecast rows (SKY-82 A4, Commit 3).

Adds ``erp_revenue_forecast`` - one persisted row per (tenant, forecast
month) produced by the finance revenue-forecast API (SMA-6 flat with a
±1.5 sigma confidence band from walk-forward historical error). The forecast is
a computed product, not source-of-truth data: the weekly recompute job (or a
manual ``POST /finance/forecast/revenue/refresh``) overwrites the horizon via
``UNIQUE (tenant_id, month)`` upsert.

The extra ``UNIQUE`` is the recompute guard: a stale second row for the same
month is a programming error, and the constraint makes it fail loudly instead
of silently double-counting a month in the UI series.

Table follows the ``ai_``-style conventions from 0033: tenant-scoped, RLS
enabled, composite ``(tenant_id, id)`` primary key.

Revision ID: 0045
Revises: 0044
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation_{table} ON public.{table} "
        "USING (tenant_id = public.current_tenant_id()) "
        "WITH CHECK (tenant_id = public.current_tenant_id())"
    )


def _disable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON public.{table}")


def upgrade() -> None:
    op.create_table(
        "erp_revenue_forecast",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("predicted", sa.Numeric(19, 4), nullable=False),
        sa.Column("lower_bound", sa.Numeric(19, 4), nullable=True),
        sa.Column("upper_bound", sa.Numeric(19, 4), nullable=True),
        sa.Column("sigma", sa.Numeric(19, 4), nullable=True),
        sa.Column("backtest_mape", sa.Numeric(9, 6), nullable=True),
        sa.Column(
            "model_version", sa.String(32), nullable=False, server_default=sa.text("'sma-6'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "month", name="uq_erp_revenue_forecast_tenant_month"),
    )
    _enable_rls("erp_revenue_forecast")


def downgrade() -> None:
    _disable_rls("erp_revenue_forecast")
    op.drop_table("erp_revenue_forecast")
