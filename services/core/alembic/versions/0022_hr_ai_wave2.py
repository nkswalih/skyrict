"""HR/Payroll AI wave 2 tables (HR-AI-002).

Continues the HR/Payroll AI slice begun in 0021 with the wave-2 feature set
from ``docs/modules/skyrict-ai/hr-payroll-ai-features.md`` §8.1/8.2 (Employee
Data Quality Scoring 8.1.3, Balance Utilization Alerts 8.1.4, Leave Pattern
Anomaly Detection 8.2.1, Smart Leave Suggestions 8.2.4) plus the model
evaluation harness for the SKY-72 attrition model.

Tables (all tenant-scoped with RLS, composite ``(tenant_id, id)`` PKs, and
composite FKs to ``erp_employees`` where they reference a person):

  - ``ai_hr_quality_scores``       per-employee data-quality score + weighted breakdown
  - ``ai_hr_utilization_alerts``   forfeit-risk / negative-accrual alert findings
  - ``ai_hr_leave_anomalies``      leave pattern anomaly findings (the "inbox")
  - ``ai_hr_leave_suggestions``    smart leave-window suggestions (prefill markers)
  - ``hr_eval_runs``               model eval-harness precision results

Status enums are kept consistent with the sibling wave-1 tables
(``ai_payroll_anomaly_log`` / ``ai_compliance_checks``): alerts and anomalies
use ``open|acknowledged|dismissed|resolved``; suggestions use
``pending|used|dismissed``.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
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
    # --- ai_hr_quality_scores -------------------------------------------------
    op.create_table(
        "ai_hr_quality_scores",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["erp_employees.tenant_id", "erp_employees.id"],
            name="fk_ai_hr_quality_scores_employee",
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("grade", sa.String(4), nullable=False),
        # Weighted sub-scores: mandatory 0.50, contact 0.25, document 0.25.
        sa.Column("mandatory_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("contact_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("document_score", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "issues", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "grade IN ('A', 'B', 'C', 'D', 'F')",
            name="ck_ai_hr_quality_scores_grade",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "generated_at",
            name="uq_ai_hr_quality_scores_employee_run",
        ),
    )
    op.create_index(
        "ix_ai_hr_quality_scores_tenant_grade",
        "ai_hr_quality_scores",
        ["tenant_id", "grade"],
    )
    op.create_index(
        "ix_ai_hr_quality_scores_tenant_generated",
        "ai_hr_quality_scores",
        ["tenant_id", "generated_at"],
    )
    _enable_rls("ai_hr_quality_scores")

    # --- ai_hr_utilization_alerts --------------------------------------------
    op.create_table(
        "ai_hr_utilization_alerts",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["erp_employees.tenant_id", "erp_employees.id"],
            name="fk_ai_hr_utilization_alerts_employee",
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("alert_type", sa.String(24), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("balance_days", sa.Integer(), nullable=False),
        # Projected days that would be forfeited (forfeit-risk) at year end.
        sa.Column("projected_forfeiture_days", sa.Integer(), nullable=True),
        sa.Column("days_remaining_in_year", sa.Integer(), nullable=True),
        sa.Column(
            "evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(14), nullable=False, server_default="open"),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "alert_type IN ('forfeit_risk', 'negative_accrual')",
            name="ck_ai_hr_utilization_alerts_type",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_hr_utilization_alerts_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'dismissed', 'resolved')",
            name="ck_ai_hr_utilization_alerts_status",
        ),
    )
    op.create_index(
        "ix_ai_hr_utilization_alerts_tenant_status",
        "ai_hr_utilization_alerts",
        ["tenant_id", "status", "severity"],
    )
    _enable_rls("ai_hr_utilization_alerts")

    # --- ai_hr_leave_anomalies -----------------------------------------------
    op.create_table(
        "ai_hr_leave_anomalies",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["erp_employees.tenant_id", "erp_employees.id"],
            name="fk_ai_hr_leave_anomalies_employee",
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("anomaly_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("team_size", sa.Integer(), nullable=True),
        sa.Column(
            "evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(14), nullable=False, server_default="open"),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_hr_leave_anomalies_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'dismissed', 'resolved')",
            name="ck_ai_hr_leave_anomalies_status",
        ),
    )
    op.create_index(
        "ix_ai_hr_leave_anomalies_tenant_status",
        "ai_hr_leave_anomalies",
        ["tenant_id", "status", "severity"],
    )
    _enable_rls("ai_hr_leave_anomalies")

    # --- ai_hr_leave_suggestions ---------------------------------------------
    op.create_table(
        "ai_hr_leave_suggestions",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["erp_employees.tenant_id", "erp_employees.id"],
            name="fk_ai_hr_leave_suggestions_employee",
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("leave_type", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        # Why-suggested breakdown: [{reason, detail, weight}] JSONB.
        sa.Column(
            "reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'used', 'dismissed')",
            name="ck_ai_hr_leave_suggestions_status",
        ),
        sa.CheckConstraint("days > 0", name="ck_ai_hr_leave_suggestions_days_positive"),
    )
    op.create_index(
        "ix_ai_hr_leave_suggestions_tenant_employee",
        "ai_hr_leave_suggestions",
        ["tenant_id", "employee_id", "status"],
    )
    _enable_rls("ai_hr_leave_suggestions")

    # --- hr_eval_runs ---------------------------------------------------------
    op.create_table(
        "hr_eval_runs",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("precision", sa.Numeric(5, 4), nullable=False),
        sa.Column("considered", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Numeric(5, 4), nullable=True),
        sa.Column("met_threshold", sa.Boolean(), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_hr_eval_runs_tenant_model",
        "hr_eval_runs",
        ["tenant_id", "model_name", "generated_at"],
    )
    _enable_rls("hr_eval_runs")


def downgrade() -> None:
    _disable_rls("hr_eval_runs")
    _disable_rls("ai_hr_leave_suggestions")
    _disable_rls("ai_hr_leave_anomalies")
    _disable_rls("ai_hr_utilization_alerts")
    _disable_rls("ai_hr_quality_scores")

    op.drop_index("ix_hr_eval_runs_tenant_model", table_name="hr_eval_runs")
    op.drop_table("hr_eval_runs")

    op.drop_index(
        "ix_ai_hr_leave_suggestions_tenant_employee", table_name="ai_hr_leave_suggestions"
    )
    op.drop_table("ai_hr_leave_suggestions")

    op.drop_index("ix_ai_hr_leave_anomalies_tenant_status", table_name="ai_hr_leave_anomalies")
    op.drop_table("ai_hr_leave_anomalies")

    op.drop_index(
        "ix_ai_hr_utilization_alerts_tenant_status", table_name="ai_hr_utilization_alerts"
    )
    op.drop_table("ai_hr_utilization_alerts")

    op.drop_index("ix_ai_hr_quality_scores_tenant_grade", table_name="ai_hr_quality_scores")
    op.drop_index("ix_ai_hr_quality_scores_tenant_generated", table_name="ai_hr_quality_scores")
    op.drop_table("ai_hr_quality_scores")
