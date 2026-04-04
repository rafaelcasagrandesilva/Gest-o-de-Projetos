"""Cenário PREVISTO vs REALIZADO (receitas, alocações, usos de frota, custos fixos projeto, estrutura operacional).

Revision ID: 0015_previsto_realizado
Revises: 0014_rbac_three_roles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_previsto_realizado"
down_revision = "0014_rbac_three_roles"
branch_labels = None
depends_on = None


scenario_enum = postgresql.ENUM("PREVISTO", "REALIZADO", name="scenario_kind", create_type=False)

# Cast explícito no PostgreSQL para colunas ENUM (evita default inválido).
_SCENARIO_DEFAULT = sa.text("'REALIZADO'::scenario_kind")


def upgrade() -> None:
    bind = op.get_bind()
    scenario_enum.create(bind, checkfirst=True)

    op.drop_constraint("uq_revenue_comp_desc", "revenues", type_="unique")
    op.add_column(
        "revenues",
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
    )
    op.create_unique_constraint(
        "uq_revenue_comp_desc_scenario",
        "revenues",
        ["project_id", "competencia", "description", "scenario"],
    )

    op.drop_constraint("uq_employee_project_start", "employee_allocations", type_="unique")
    op.add_column(
        "employee_allocations",
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
    )
    op.create_unique_constraint(
        "uq_employee_project_start_scenario",
        "employee_allocations",
        ["employee_id", "project_id", "start_date", "scenario"],
    )

    op.drop_constraint("uq_vehicle_project_date", "vehicle_usages", type_="unique")
    op.add_column(
        "vehicle_usages",
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
    )
    op.create_unique_constraint(
        "uq_vehicle_project_date_scenario",
        "vehicle_usages",
        ["vehicle_id", "project_id", "usage_date", "scenario"],
    )

    op.drop_constraint("uq_project_fixed_cost", "project_fixed_costs", type_="unique")
    op.add_column(
        "project_fixed_costs",
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
    )
    op.create_unique_constraint(
        "uq_project_fixed_cost_scenario",
        "project_fixed_costs",
        ["project_id", "competencia", "name", "scenario"],
    )

    op.drop_constraint("uq_project_labors_project_employee_competencia", "project_labors", type_="unique")
    op.add_column(
        "project_labors",
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
    )
    op.create_unique_constraint(
        "uq_project_labors_proj_emp_comp_scenario",
        "project_labors",
        ["project_id", "employee_id", "competencia", "scenario"],
    )

    op.drop_constraint("uq_project_vehicles_project_vehicle_competencia", "project_vehicles", type_="unique")
    op.add_column(
        "project_vehicles",
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
    )
    op.create_unique_constraint(
        "uq_project_vehicles_proj_veh_comp_scenario",
        "project_vehicles",
        ["project_id", "vehicle_id", "competencia", "scenario"],
    )

    op.add_column(
        "project_system_costs",
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
    )
    op.add_column(
        "project_operational_fixed",
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
    )

    op.execute(sa.text("UPDATE revenues SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL"))
    op.execute(sa.text("UPDATE employee_allocations SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL"))
    op.execute(sa.text("UPDATE vehicle_usages SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL"))
    op.execute(sa.text("UPDATE project_fixed_costs SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL"))
    op.execute(sa.text("UPDATE project_labors SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL"))
    op.execute(sa.text("UPDATE project_vehicles SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL"))
    op.execute(sa.text("UPDATE project_system_costs SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL"))
    op.execute(sa.text("UPDATE project_operational_fixed SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL"))

    for tbl in (
        "revenues",
        "employee_allocations",
        "vehicle_usages",
        "project_fixed_costs",
        "project_labors",
        "project_vehicles",
        "project_system_costs",
        "project_operational_fixed",
    ):
        op.alter_column(tbl, "scenario", server_default=None)

    op.create_index("ix_revenues_scenario", "revenues", ["scenario"], unique=False)
    op.create_index("ix_project_labors_scenario", "project_labors", ["scenario"], unique=False)
    op.create_index("ix_project_vehicles_scenario", "project_vehicles", ["scenario"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_vehicles_scenario", table_name="project_vehicles")
    op.drop_index("ix_project_labors_scenario", table_name="project_labors")
    op.drop_index("ix_revenues_scenario", table_name="revenues")

    op.drop_column("project_operational_fixed", "scenario")
    op.drop_column("project_system_costs", "scenario")

    op.drop_constraint("uq_project_vehicles_proj_veh_comp_scenario", "project_vehicles", type_="unique")
    op.drop_column("project_vehicles", "scenario")
    op.create_unique_constraint(
        "uq_project_vehicles_project_vehicle_competencia",
        "project_vehicles",
        ["project_id", "vehicle_id", "competencia"],
    )

    op.drop_constraint("uq_project_labors_proj_emp_comp_scenario", "project_labors", type_="unique")
    op.drop_column("project_labors", "scenario")
    op.create_unique_constraint(
        "uq_project_labors_project_employee_competencia",
        "project_labors",
        ["project_id", "employee_id", "competencia"],
    )

    op.drop_constraint("uq_project_fixed_cost_scenario", "project_fixed_costs", type_="unique")
    op.drop_column("project_fixed_costs", "scenario")
    op.create_unique_constraint(
        "uq_project_fixed_cost",
        "project_fixed_costs",
        ["project_id", "competencia", "name"],
    )

    op.drop_constraint("uq_vehicle_project_date_scenario", "vehicle_usages", type_="unique")
    op.drop_column("vehicle_usages", "scenario")
    op.create_unique_constraint(
        "uq_vehicle_project_date",
        "vehicle_usages",
        ["vehicle_id", "project_id", "usage_date"],
    )

    op.drop_constraint("uq_employee_project_start_scenario", "employee_allocations", type_="unique")
    op.drop_column("employee_allocations", "scenario")
    op.create_unique_constraint(
        "uq_employee_project_start",
        "employee_allocations",
        ["employee_id", "project_id", "start_date"],
    )

    op.drop_constraint("uq_revenue_comp_desc_scenario", "revenues", type_="unique")
    op.drop_column("revenues", "scenario")
    op.create_unique_constraint(
        "uq_revenue_comp_desc",
        "revenues",
        ["project_id", "competencia", "description"],
    )

    scenario_enum.drop(op.get_bind(), checkfirst=True)
