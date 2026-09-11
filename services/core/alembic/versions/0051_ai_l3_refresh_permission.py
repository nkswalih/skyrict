"""Seed the erp.ai.l3.refresh permission key (HR-AI-003 L3 refresh gate).

The ``erp.ai.l3.refresh`` key gates force-refreshing an L3 HR/Payroll AI
narrative (POST /api/v1/ai/l3/{kind}/refresh) alongside the read gate
``erp.hr.ai.management``, mirroring how ``erp.ai.narrator.refresh`` gates the
SKY-63 narrator refresh. It enters the runtime catalog (``core_permissions``)
the same way, so ``require_all_permissions`` can enforce it at the core edge.
Identity (0026) seeds the same string for role grants.

Revision ID: 0046
Revises: 0050
Create Date: 2026-09-09
"""

from __future__ import annotations

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

_KEY = "erp.ai.l3.refresh"
_DESCRIPTION = "Force-refresh an L3 HR/Payroll AI narrative (requires erp.hr.ai.management too)"


def upgrade() -> None:
    op.execute(
        "INSERT INTO core_permissions (key, description) VALUES "
        f"('{_KEY}', '{_DESCRIPTION}') ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM core_permissions WHERE key = '{_KEY}'")  # nosec B608
