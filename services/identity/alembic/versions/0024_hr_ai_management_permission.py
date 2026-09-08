"""Add erp.hr.ai.management permission key (HR-AI-003 L3 analytics).

Ticket HR-AI-003 (docs/modules/skyrict-ai/hr-payroll-ai-features.md §L3):
``erp.hr.ai.management`` gates every L3 HR/Payroll AI narrative feature -
payroll-cost narratives, leave-pay correlation, and compliance monitoring
digests. The key is deliberately high-tier: like ``erp.hr.ai.individual``
(0020), it is granted ONLY to ``tenant_owner`` and stays out of the default
org_admin/dept_manager grants, so L3 leadership narratives stay owner-scoped
until a dedicated executive role is provisioned. Aggregates only (no
employee-level data), as the L3 scope defines.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-08
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

# (key, description) - mirrors identity.core.permissions catalog entries.
_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("erp.hr.ai.management", "View L3 HR/Payroll AI narratives (cost, correlation, compliance digest)"),
)

# Roles granted each key when migrating (owner is covered by its "*" grant).
# L3 is exec-scoped: tenant_owner ONLY, mirroring the 0020 "individual" tier.
_GRANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("erp.hr.ai.management", ("tenant_owner",)),
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