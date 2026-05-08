"""vehicle soft delete

Revision ID: 0043_vehicle_soft_delete
Revises: 0042_project_closed_deleted_timestamptz
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_vehicle_soft_delete"
down_revision = "0042_project_closed_deleted_timestamptz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_vehicles_deleted_at", "vehicles", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_vehicles_deleted_at", table_name="vehicles")
    op.drop_column("vehicles", "deleted_at")

