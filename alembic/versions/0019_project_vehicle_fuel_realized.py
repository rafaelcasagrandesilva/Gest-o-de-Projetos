"""project_vehicles: fuel_cost_realized; km e fuel_type opcionais (REALIZADO).

Revision ID: 0019_pv_fuel_real
Revises: 0018_company_staff_costs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_pv_fuel_real"
down_revision = "0018_company_staff_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_vehicles",
        sa.Column("fuel_cost_realized", sa.Numeric(14, 2), nullable=True),
    )
    op.alter_column("project_vehicles", "km_per_month", existing_type=sa.Numeric(14, 2), nullable=True)
    op.alter_column("project_vehicles", "fuel_type", existing_type=sa.String(length=20), nullable=True)

    # Preserva totais já gravados: linhas REALIZADO antigas usavam cálculo por km; passam a usar valor manual = custo atual.
    op.execute(
        """
        UPDATE project_vehicles
        SET fuel_cost_realized = monthly_cost
        WHERE scenario = 'REALIZADO'::scenario_kind AND fuel_cost_realized IS NULL
        """
    )


def downgrade() -> None:
    op.alter_column("project_vehicles", "fuel_type", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("project_vehicles", "km_per_month", existing_type=sa.Numeric(14, 2), nullable=False)
    op.drop_column("project_vehicles", "fuel_cost_realized")
