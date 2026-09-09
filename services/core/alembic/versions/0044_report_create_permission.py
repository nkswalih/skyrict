"""Seed the erp.reports.create permission (RPT-AI-001, SKY-80).

The NL report builder lets an authorised user persist a generated report spec
as a NEW ``erp_report_definitions`` row. That write path is gated by a
dedicated ``erp.reports.create`` permission (distinct from the read gate every
existing definition endpoint already enforces), so a user who can RUN reports
is not automatically granted the right to CREATE new ones.

This migration only seeds the permission key into ``core_permissions`` (same
``ON CONFLICT DO NOTHING`` pattern as 0036/0030) - it adds no schema and no
data beyond the catalog row.

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-08
"""

from __future__ import annotations

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

_REPORTS_CREATE_KEY = "erp.reports.create"
_REPORTS_CREATE_DESCRIPTION = "Create new reporting definitions (NL report builder)"


def upgrade() -> None:
    op.execute(
        "INSERT INTO core_permissions (key, description) VALUES "
        f"('{_REPORTS_CREATE_KEY}', '{_REPORTS_CREATE_DESCRIPTION}') "  # nosec B608
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM core_permissions WHERE key = '{_REPORTS_CREATE_KEY}'")  # nosec B608
