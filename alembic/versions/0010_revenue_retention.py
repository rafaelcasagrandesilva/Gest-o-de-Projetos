"""revenues: has_retention (10% retenção)

Revision ID: 0010_revenue_retention
Revises: 0009_fleet_project_vehicles
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0010_revenue_retention"
down_revision = "0009_fleet_project_vehicles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "revenues",
        sa.Column("has_retention", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("revenues", "has_retention", server_default=None)


def downgrade() -> None:
    op.drop_column("revenues", "has_retention")
