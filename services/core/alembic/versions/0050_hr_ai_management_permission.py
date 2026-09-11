"""Seed the erp.hr.ai.management permission key (HR-AI-003 L3 analytics).

The ``erp.hr.ai.management`` key gates every L3 HR/Payroll AI narrative
endpoint - payroll-cost narratives, leave-pay correlation, and compliance
monitoring digests. It enters the runtime catalog (``core_permissions``)
exactly like its ``erp.hr.ai.*`` siblings in migration 0021 and the
``erp.hr.ai.eval`` key in 0023, so ``require_permission`` can enforce it at
the core edge. Identity (0025) seeds the same string for role grants.

Revision ID: 0045
Revises: 0049
Create Date: 2026-09-08
"""

from __future__ import annotations

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

_KEY = "erp.hr.ai.management"
_DESCRIPTION = "View L3 HR/Payroll AI narratives (cost, correlation, compliance digest)"


def upgrade() -> None:
    op.execute(
        "INSERT INTO core_permissions (key, description) VALUES "
        f"('{_KEY}', '{_DESCRIPTION}') ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM core_permissions WHERE key = '{_KEY}'")  # nosec B608
