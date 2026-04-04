"""Garante coluna scenario + enum scenario_kind (idempotente).

Cobre ambientes em que 0015 não rodou, falhou no meio ou o banco foi restaurado sem as colunas.

Revision ID: 0016_scenario_columns_ensure
Revises: 0015_previsto_realizado
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_scenario_columns_ensure"
down_revision = "0015_previsto_realizado"
branch_labels = None
depends_on = None

_SCENARIO_DEFAULT = sa.text("'REALIZADO'::scenario_kind")

SCENARIO_TABLES = (
    "revenues",
    "employee_allocations",
    "vehicle_usages",
    "project_fixed_costs",
    "project_labors",
    "project_vehicles",
    "project_system_costs",
    "project_operational_fixed",
)


def _column_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _unique_names(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return set()
    return {u["name"] for u in insp.get_unique_constraints(table) if u.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        sa.text("""
DO $$ BEGIN
    CREATE TYPE scenario_kind AS ENUM ('PREVISTO', 'REALIZADO');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
""")
    )

    scenario_enum = postgresql.ENUM("PREVISTO", "REALIZADO", name="scenario_kind", create_type=False)

    # --- revenues ---
    if _column_exists(bind, "revenues", "scenario") is False:
        uks = _unique_names(bind, "revenues")
        if "uq_revenue_comp_desc" in uks:
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

    # --- employee_allocations ---
    if _column_exists(bind, "employee_allocations", "scenario") is False:
        uks = _unique_names(bind, "employee_allocations")
        if "uq_employee_project_start" in uks:
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

    # --- vehicle_usages ---
    if _column_exists(bind, "vehicle_usages", "scenario") is False:
        uks = _unique_names(bind, "vehicle_usages")
        if "uq_vehicle_project_date" in uks:
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

    # --- project_fixed_costs ---
    if _column_exists(bind, "project_fixed_costs", "scenario") is False:
        uks = _unique_names(bind, "project_fixed_costs")
        if "uq_project_fixed_cost" in uks:
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

    # --- project_labors ---
    if _column_exists(bind, "project_labors", "scenario") is False:
        uks = _unique_names(bind, "project_labors")
        if "uq_project_labors_project_employee_competencia" in uks:
            op.drop_constraint(
                "uq_project_labors_project_employee_competencia", "project_labors", type_="unique"
            )
        op.add_column(
            "project_labors",
            sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
        )
        op.create_unique_constraint(
            "uq_project_labors_proj_emp_comp_scenario",
            "project_labors",
            ["project_id", "employee_id", "competencia", "scenario"],
        )

    # --- project_vehicles ---
    if _column_exists(bind, "project_vehicles", "scenario") is False:
        uks = _unique_names(bind, "project_vehicles")
        if "uq_project_vehicles_project_vehicle_competencia" in uks:
            op.drop_constraint(
                "uq_project_vehicles_project_vehicle_competencia", "project_vehicles", type_="unique"
            )
        op.add_column(
            "project_vehicles",
            sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
        )
        op.create_unique_constraint(
            "uq_project_vehicles_proj_veh_comp_scenario",
            "project_vehicles",
            ["project_id", "vehicle_id", "competencia", "scenario"],
        )

    # --- project_system_costs ---
    if _column_exists(bind, "project_system_costs", "scenario") is False:
        op.add_column(
            "project_system_costs",
            sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
        )

    # --- project_operational_fixed ---
    if _column_exists(bind, "project_operational_fixed", "scenario") is False:
        op.add_column(
            "project_operational_fixed",
            sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
        )

    # Backfill + remover server_default (usa information_schema — válido no mesmo transaction após ADD)
    conn = op.get_bind()
    for tbl in SCENARIO_TABLES:
        row = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :t AND column_name = 'scenario'"
            ),
            {"t": tbl},
        ).fetchone()
        if row:
            op.execute(
                sa.text(f"UPDATE {tbl} SET scenario = 'REALIZADO'::scenario_kind WHERE scenario IS NULL")
            )
            op.alter_column(tbl, "scenario", server_default=None)

    # Índices (idempotente no PostgreSQL)
    idx_specs = (
        ("revenues", "ix_revenues_scenario"),
        ("project_labors", "ix_project_labors_scenario"),
        ("project_vehicles", "ix_project_vehicles_scenario"),
    )
    for tbl, idx in idx_specs:
        row = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :t AND column_name = 'scenario'"
            ),
            {"t": tbl},
        ).fetchone()
        if row:
            op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (scenario)"))


def downgrade() -> None:
    """Fix forward-only: não reverte cenário para evitar perda de dados."""
    pass
