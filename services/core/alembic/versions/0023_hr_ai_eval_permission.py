"""Seed the ``erp.hr.ai.eval`` permission key (HR-AI-002, Commit 5).

The ai-agent eval harness (SKY-72) reports per-metric precision results to core's
``POST /api/v1/ai/hr/eval-runs`` endpoint. Only operators holding this key (or
the owner ``*`` wildcard) may record eval runs; every read endpoint keeps its
own ``erp.hr.ai.*`` gate. The key is seeded into the runtime catalog
(``core_permissions``) exactly like its ``erp.hr.ai.*`` siblings in migration
0021.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-29
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_KEY = "erp.hr.ai.eval"
_DESCRIPTION = "Record ai-agent model eval-harness precision results"


def upgrade() -> None:
    op.execute(
        "INSERT INTO core_permissions (key, description) VALUES "
        f"('{_KEY}', '{_DESCRIPTION}') ON CONFLICT (key) DO NOTHING"  # nosec B608
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM core_permissions WHERE key = '{_KEY}'")  # nosec B608
