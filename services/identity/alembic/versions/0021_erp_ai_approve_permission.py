"""Add erp.inventory.ai.approve permission for AI restock suggestion workflow.

Ticket SKY-68 (inventory AI advisor suite): approve/reject AI restock
suggestions and trigger scans require a dedicated permission separate from
erp.inventory.write. Granted to organization_admin and department_manager.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_PERMISSIONS: tuple[tuple[str, str], ...] = (
    (
        "erp.inventory.ai.approve",
        "Approve or reject AI-generated restock suggestions",
    ),
)

_ALL = tuple(key for key, _ in _PERMISSIONS)


def _append_permissions(role_names: tuple[str, ...], permission_keys: tuple[str, ...]) -> None:
    """Append missing keys without disturbing tenant-specific role grants."""
    for key in permission_keys:
        op.execute(
            "UPDATE roles SET permissions = array_append(permissions, "
            f"'{key}') WHERE name IN ({', '.join(repr(name) for name in role_names)}) "
            f"AND NOT ('{key}' = ANY(permissions))"
        )


def upgrade() -> None:
    for key, description in _PERMISSIONS:
        op.execute(
            "INSERT INTO permissions (key, description) VALUES "
            f"('{key}', '{description}') ON CONFLICT (key) DO NOTHING"
        )

    _append_permissions(("organization_admin", "department_manager"), _ALL)


def downgrade() -> None:
    for key in _ALL:
        op.execute(f"UPDATE roles SET permissions = array_remove(permissions, '{key}')")
        op.execute(f"DELETE FROM permissions WHERE key = '{key}'")
