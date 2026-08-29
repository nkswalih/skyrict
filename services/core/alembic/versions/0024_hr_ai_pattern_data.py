"""HR-AI-002 pattern-engine input tables (holidays + blackout periods).

The leave-pattern anomaly detector (8.2.1) and the smart leave-window
suggestion engine (8.2.4) are driven by tenant-defined inputs that live
outside the ERP leave tables:

  - ``ai_hr_public_holidays``      the per-tenant holiday calendar the
    ``pre_holiday_spike`` anomaly compares leave spans against (org-wide rows
    carry ``department_id`` NULL; rows may also be stamped to one department).
  - ``ai_hr_leave_blackout_periods`` the per-tenant blackout windows the
    suggestion engine must steer suggested leave away from (``department_id``
    NULL = org-wide).

Both are tenant-scoped with the same composite-PK + RLS convention as every
sibling ``ai_*`` table. They are lookup/config data — no employee PII, no
signal tables — written via the existing ``erp.hr.write`` gate and consumed
server-side by the AI engines under tenant context.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
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
    # --- ai_hr_public_holidays ------------------------------------------------
    op.create_table(
        "ai_hr_public_holidays",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("calendar_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["erp_departments.tenant_id", "erp_departments.id"],
            name="fk_ai_hr_public_holidays_department",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "department_id",
            "calendar_date",
            name="uq_ai_hr_public_holidays_dept_date",
        ),
    )
    op.create_index(
        "ix_ai_hr_public_holidays_tenant_date",
        "ai_hr_public_holidays",
        ["tenant_id", "calendar_date"],
    )
    _enable_rls("ai_hr_public_holidays")

    # --- ai_hr_leave_blackout_periods ----------------------------------------
    op.create_table(
        "ai_hr_leave_blackout_periods",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["erp_departments.tenant_id", "erp_departments.id"],
            name="fk_ai_hr_leave_blackout_periods_department",
        ),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "end_date >= start_date",
            name="ck_ai_hr_leave_blackout_periods_range",
        ),
    )
    op.create_index(
        "ix_ai_hr_leave_blackout_periods_tenant_start",
        "ai_hr_leave_blackout_periods",
        ["tenant_id", "start_date"],
    )
    _enable_rls("ai_hr_leave_blackout_periods")


def downgrade() -> None:
    _disable_rls("ai_hr_leave_blackout_periods")
    _disable_rls("ai_hr_public_holidays")

    op.drop_index(
        "ix_ai_hr_leave_blackout_periods_tenant_start",
        table_name="ai_hr_leave_blackout_periods",
    )
    op.drop_table("ai_hr_leave_blackout_periods")

    op.drop_index(
        "ix_ai_hr_public_holidays_tenant_date",
        table_name="ai_hr_public_holidays",
    )
    op.drop_table("ai_hr_public_holidays")
