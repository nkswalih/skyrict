"""Add erp.documents.* permission keys (SKY-87 document management).

Ticket SKY-87 (docs/modules/documents.md): the three ``erp.documents.*`` keys
gate the document management platform surface at the core edge. Core's
``core_permissions`` catalog carries the same keys (migration 0048); this
migration mirrors them into identity's ``permissions`` table so role grants
stay portable across the platform (same precedent as 0020 for ``erp.hr.ai.*``
and 0023 for ``erp.payroll.ai.*``).

Grant matrix:
  - ``erp.documents.read``   -> organization_admin (read/upload-gated reads)
  - ``erp.documents.write``  -> organization_admin
  - ``erp.documents.delete`` -> organization_admin

Tenant owners pass via the ``*`` wildcard grant (mirroring 0020 / 0022 / 0023).
Entity-linked documents additionally require the owning module's read key;
role sets already grant those for their respective modules.

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
    ("erp.documents.read", "View documents and their extracted content"),
    ("erp.documents.write", "Upload, update, and merge documents"),
    ("erp.documents.delete", "Hard-delete document versions and metadata"),
)

# Roles granted each key when migrating (owner is covered by its "*" grant).
_GRANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("erp.documents.read", ("organization_admin",)),
    ("erp.documents.write", ("organization_admin",)),
    ("erp.documents.delete", ("organization_admin",)),
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
