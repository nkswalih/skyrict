"""Revenue forecast pipeline weighting (SKY-82 A4, Commit 4).

Adds ``pipeline_value`` to ``erp_revenue_forecast`` - the run-level total of
weighted expected pipeline (open CRM opportunities valued at
``probability/100 x amount``, bucketed by ``expected_close_date``) blended
into the forecast horizon. ``NULL`` means the forecast abstained or predates
this feature; a recompute overwrites it alongside the horizon via the existing
``UNIQUE (tenant_id, month)`` upsert.

Revision ID: 0046
Revises: 0045
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "erp_revenue_forecast",
        sa.Column("pipeline_value", sa.Numeric(19, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("erp_revenue_forecast", "pipeline_value")
