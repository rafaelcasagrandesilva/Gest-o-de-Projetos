"""enterprise financial: employees, allocations, revenues, project_costs

Revision ID: 0002_enterprise_financial
Revises: 0001_init
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0002_enterprise_financial"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("employment_type", sa.String(length=10), nullable=False, server_default="CLT"))
    op.add_column("employees", sa.Column("salary_base", sa.Numeric(14, 2), nullable=True))
    op.add_column("employees", sa.Column("additional_costs", sa.Numeric(14, 2), nullable=True))
    op.add_column("employees", sa.Column("total_cost", sa.Numeric(14, 2), nullable=True))
    op.execute(sa.text("UPDATE employees SET total_cost = COALESCE(monthly_cost, 0)"))
    op.alter_column("employees", "total_cost", nullable=False, server_default="0")
    op.drop_column("employees", "monthly_cost")
    op.execute(sa.text("ALTER TABLE employees ALTER COLUMN employment_type DROP DEFAULT"))

    op.add_column(
        "employee_allocations",
        sa.Column("monthly_cost", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "employee_allocations",
        sa.Column("hours_allocated", sa.Numeric(10, 2), nullable=True),
    )

    op.add_column(
        "revenues",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="recebido"),
    )
    op.execute(sa.text("ALTER TABLE revenues ALTER COLUMN status DROP DEFAULT"))

    op.create_table(
        "project_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cost_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("cost_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
    )
    op.create_index("ix_project_costs_project_id", "project_costs", ["project_id"], unique=False)
    op.create_index("ix_project_costs_cost_date", "project_costs", ["cost_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_costs_cost_date", table_name="project_costs")
    op.drop_index("ix_project_costs_project_id", table_name="project_costs")
    op.drop_table("project_costs")

    op.drop_column("revenues", "status")

    op.drop_column("employee_allocations", "hours_allocated")
    op.drop_column("employee_allocations", "monthly_cost")

    op.add_column("employees", sa.Column("monthly_cost", sa.Numeric(14, 2), nullable=True))
    op.execute(sa.text("UPDATE employees SET monthly_cost = total_cost"))
    op.drop_column("employees", "total_cost")
    op.drop_column("employees", "additional_costs")
    op.drop_column("employees", "salary_base")
    op.drop_column("employees", "employment_type")
