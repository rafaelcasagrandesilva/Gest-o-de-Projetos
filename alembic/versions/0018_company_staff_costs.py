"""Tabela company_staff_costs (custos adm por colaborador/mês/cenário).

Revision ID: 0018_company_staff_costs
Revises: 0017_proj_labor_costs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_company_staff_costs"
down_revision = "0017_proj_labor_costs"
branch_labels = None
depends_on = None

scenario_enum = postgresql.ENUM("PREVISTO", "REALIZADO", name="scenario_kind", create_type=False)
_SCENARIO_DEFAULT = sa.text("'REALIZADO'::scenario_kind")


def upgrade() -> None:
    op.create_table(
        "company_staff_costs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("scenario", scenario_enum, nullable=False, server_default=_SCENARIO_DEFAULT),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_id",
            "competencia",
            "scenario",
            name="uq_company_staff_costs_emp_comp_sc",
        ),
    )
    op.create_index(
        "ix_company_staff_costs_competencia", "company_staff_costs", ["competencia"], unique=False
    )
    op.create_index(
        "ix_company_staff_costs_employee_id", "company_staff_costs", ["employee_id"], unique=False
    )
    op.create_index(
        "ix_company_staff_costs_scenario", "company_staff_costs", ["scenario"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_company_staff_costs_scenario", table_name="company_staff_costs")
    op.drop_index("ix_company_staff_costs_employee_id", table_name="company_staff_costs")
    op.drop_index("ix_company_staff_costs_competencia", table_name="company_staff_costs")
    op.drop_table("company_staff_costs")
