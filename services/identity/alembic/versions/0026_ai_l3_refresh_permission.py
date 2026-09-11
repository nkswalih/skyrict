"""Add erp.ai.l3.refresh permission key (HR-AI-003 L3 refresh gate).

Ticket HR-AI-003 (docs/modules/skyrict-ai/hr-payroll-ai-features.md §L3):
``erp.ai.l3.refresh`` gates force-refreshing an L3 HR/Payroll AI narrative on
POST /api/v1/ai/l3/{kind}/refresh, layered on top of the read gate
``erp.hr.ai.management`` (0025) - the same two-tier convention as
``erp.ai.narrator.refresh`` (0022). Granted ONLY to ``tenant_owner`` so the
owner can always demo a refresh; org_admin/dept_manager hold neither key and
stay 403 on both read and refresh.

Revision ID: 0025
Revises: 0025
Create Date: 2026-09-09
"""

from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

# (key, description) - mirrors identity.core.permissions catalog entries.
_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("erp.ai.l3.refresh", "Force-refresh an L3 HR/Payroll AI narrative"),
)

# Roles granted each key when migrating (owner is covered by its "*" grant).
_GRANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("erp.ai.l3.refresh", ("tenant_owner",)),
)


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

    for key, role_names in _GRANTS:
        _append_permissions(role_names, (key,))


def downgrade() -> None:
    all_keys = tuple(key for key, _ in _PERMISSIONS)
    for key in all_keys:
        op.execute(f"UPDATE roles SET permissions = array_remove(permissions, '{key}')")
        op.execute(f"DELETE FROM permissions WHERE key = '{key}'")
