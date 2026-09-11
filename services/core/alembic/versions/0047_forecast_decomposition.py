"""Revenue forecast per-month decomposition (SKY-82 A4, Commit 5).

Extends ``erp_revenue_forecast`` with ``baseline`` and ``pipeline_uplift`` -
the per-month split of ``predicted`` back into the trend + seasonal projection
and the CRM weighted-pipeline uplift blended in (``predicted == baseline +
pipeline_uplift``). Lets the UI show *why* a month is high (e.g. a large
expected close) without re-running the model. ``NULL`` means the row predates
this migration; a recompute overwrites both columns via the existing
``UNIQUE (tenant_id, month)`` upsert.

Revision ID: 0047
Revises: 0046
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "erp_revenue_forecast",
        sa.Column("baseline", sa.Numeric(19, 4), nullable=True),
    )
    op.add_column(
        "erp_revenue_forecast",
        sa.Column("pipeline_uplift", sa.Numeric(19, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("erp_revenue_forecast", "pipeline_uplift")
    op.drop_column("erp_revenue_forecast", "baseline")
