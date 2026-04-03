"""vehicles: tipo e condutor; project_vehicles: FK frota

Revision ID: 0009_fleet_project_vehicles
Revises: 0008_labor_alloc_pct
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_fleet_project_vehicles"
down_revision = "0008_labor_alloc_pct"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vehicles",
        sa.Column("vehicle_type", sa.String(length=20), nullable=False, server_default="LIGHT"),
    )
    op.alter_column("vehicles", "vehicle_type", server_default=None)
    op.add_column(
        "vehicles",
        sa.Column(
            "driver_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.execute(sa.text("DELETE FROM project_vehicles"))
    op.drop_column("project_vehicles", "vehicle_type")
    op.add_column(
        "project_vehicles",
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_project_vehicles_project_vehicle_competencia",
        "project_vehicles",
        ["project_id", "vehicle_id", "competencia"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_project_vehicles_project_vehicle_competencia", "project_vehicles", type_="unique")
    op.drop_constraint("project_vehicles_vehicle_id_fkey", "project_vehicles", type_="foreignkey")
    op.drop_column("project_vehicles", "vehicle_id")
    op.add_column(
        "project_vehicles",
        sa.Column("vehicle_type", sa.String(length=20), nullable=False, server_default="LIGHT"),
    )
    op.alter_column("project_vehicles", "vehicle_type", server_default=None)
    op.drop_constraint("vehicles_driver_employee_id_fkey", "vehicles", type_="foreignkey")
    op.drop_column("vehicles", "driver_employee_id")
    op.drop_column("vehicles", "vehicle_type")
