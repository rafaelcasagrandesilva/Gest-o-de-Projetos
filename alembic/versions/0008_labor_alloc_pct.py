"""project_labors: allocation_percentage (rateio %)

Revision ID: 0008_labor_alloc_pct
Revises: 0007_labors_repair
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_labor_alloc_pct"
down_revision = "0007_labors_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_labors",
        sa.Column("allocation_percentage", sa.Numeric(5, 2), nullable=False, server_default="100"),
    )
    op.alter_column("project_labors", "allocation_percentage", server_default=None)


def downgrade() -> None:
    op.drop_column("project_labors", "allocation_percentage")
