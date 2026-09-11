"""Seed the Sales Coach + Audit Guardian AI permissions (SKY-90 wave 2).

The AI proxy router (``/api/v1/ai/coaching/*``, ``/api/v1/ai/guardian/*``)
enforces ``erp.ai.invoke`` AND the module key for each action, mirroring the
narrator/supplier-risk posture. These four keys let role grants distinguish
who may read the coaching suggestion queue, decide accept/dismiss, open the
weekly guardian reports (incl. flagged-event evidence), and acknowledge a
report as reviewed - without granting the whole ERP AI surface.

This migration only seeds the permission keys into ``core_permissions`` (same
``ON CONFLICT DO NOTHING`` pattern as 0044/0036/0030) - it adds no schema and
no data beyond the catalog rows.

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-10
"""

from __future__ import annotations

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

# (key, description) pairs - order matters for a deterministic diff.
_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("erp.ai.coaching.read", "Read the Sales Coach suggestion queue"),
    ("erp.ai.coaching.review", "Accept or dismiss Sales Coach suggestions"),
    ("erp.ai.guardian.read", "Read Audit Guardian weekly reports and evidence"),
    ("erp.ai.guardian.review", "Acknowledge an Audit Guardian report as reviewed"),
)


def upgrade() -> None:
    for key, description in _PERMISSIONS:
        op.execute(
            "INSERT INTO core_permissions (key, description) VALUES "
            f"('{key}', '{description}') "  # nosec B608
            "ON CONFLICT (key) DO NOTHING"
        )


def downgrade() -> None:
    for key, _ in _PERMISSIONS:
        op.execute(f"DELETE FROM core_permissions WHERE key = '{key}'")  # nosec B608
