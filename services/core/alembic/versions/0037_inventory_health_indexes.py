"""Stock-health analytics: index + erp.inventory.cost permission (INV-ANL-001).

Two parts:

1. The stock-health analytics queries filter the immutable ledger by
   ``(tenant_id, warehouse_id, movement_type)`` and window on ``created_at``
   (dead-stock / slow-mover windows and the weekly movement-trend series). Add
   a covering composite index so those reads stay sub-second on the seed
   dataset (ticket requirement), independent of the existing write-oriented
   ``ix_erp_stock_movements_product_warehouse`` index.

2. Seed the ``erp.inventory.cost`` permission used to gate server-side the
   cost-price valuations (dead-stock tied-up capital, slow-mover carrying
   cost) returned by these reports. Unit-cost access is a distinct capability
   from ``erp.inventory.read``: read grants the aggregate counts, cost grants
   the money figures.

This was originally SKY-71 migration 0031/0032; the snapshot persistence it
shipped alongside was dropped after merging the reporting data layer (0036,
RPT-DATA-001), which owns ``erp_report_snapshots`` with a definitions-based
schema.

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-05
"""

from __future__ import annotations

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_erp_stock_movements_tenant_wh_type_created"

_PERMISSIONS: tuple[tuple[str, str], ...] = (
    (
        "erp.inventory.cost",
        "View cost-price valuations in inventory reports (dead stock / slow movers)",
    ),
)


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        "erp_stock_movements",
        ["tenant_id", "warehouse_id", "movement_type", "created_at"],
    )

    for key, description in _PERMISSIONS:
        op.execute(
            "INSERT INTO core_permissions (key, description) VALUES "
            f"('{key}', '{description}') ON CONFLICT (key) DO NOTHING"  # nosec B608
        )


def downgrade() -> None:
    for key, _ in _PERMISSIONS:
        op.execute(f"DELETE FROM core_permissions WHERE key = '{key}'")  # nosec B608

    op.drop_index(_INDEX_NAME, table_name="erp_stock_movements")
