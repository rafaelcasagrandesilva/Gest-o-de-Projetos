"""vehicles: monthly_cost (custo fixo individual)

Revision ID: 0011_vehicle_monthly_cost
Revises: 0010_revenue_retention
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_vehicle_monthly_cost"
down_revision = "0010_revenue_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vehicles",
        sa.Column("monthly_cost", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.execute(
        sa.text(
            """
            UPDATE vehicles AS v
            SET monthly_cost = COALESCE(
                CASE v.vehicle_type
                    WHEN 'LIGHT' THEN (SELECT vehicle_light_cost FROM system_settings ORDER BY id LIMIT 1)
                    WHEN 'PICKUP' THEN (SELECT vehicle_pickup_cost FROM system_settings ORDER BY id LIMIT 1)
                    WHEN 'SEDAN' THEN (SELECT vehicle_sedan_cost FROM system_settings ORDER BY id LIMIT 1)
                    ELSE (SELECT vehicle_light_cost FROM system_settings ORDER BY id LIMIT 1)
                END,
                0
            )
            """
        )
    )
    op.alter_column("vehicles", "monthly_cost", server_default=None)


def downgrade() -> None:
    op.drop_column("vehicles", "monthly_cost")
