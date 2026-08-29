"""Add erp.inventory.ai.approve permission for AI restock suggestion workflow.

Ticket SKY-68 (inventory AI advisor suite): approves/rejects AI restock
suggestions require a dedicated permission separate from erp.inventory.write.
The core AI proxy router uses this key to gate /ai/suggestions/scan,
/ai/suggestions/{id}/approve, and /ai/suggestions/{id}/reject.

Renumbered 0022 -> 0025 on merge with feat/HR-AI-002 (which owns core 0022
hr-ai wave-2, 0023 hr-ai eval permission, 0024 hr-ai pattern data): chains
this inventory permission seeding AFTER 0024 so both feature lines keep a
single linear head.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

_PERMISSIONS: tuple[tuple[str, str], ...] = (
    (
        "erp.inventory.ai.approve",
        "Approve or reject AI-generated restock suggestions",
    ),
)


def upgrade() -> None:
    for key, description in _PERMISSIONS:
        op.execute(
            "INSERT INTO core_permissions (key, description) VALUES "
            f"('{key}', '{description}') ON CONFLICT (key) DO NOTHING"
        )


def downgrade() -> None:
    for key, _ in _PERMISSIONS:
        op.execute(f"DELETE FROM core_permissions WHERE key = '{key}'")
