"""project_labors: apenas vínculo employee + competência

Revision ID: 0006_project_labor_employee_only
Revises: 0005_pj_additional_cost
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006_project_labor_employee_only"
down_revision = "0005_pj_additional_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM project_labors WHERE employee_id IS NULL"))
    op.drop_column("project_labors", "monthly_cost")
    op.drop_column("project_labors", "hours_per_month")
    op.drop_column("project_labors", "hourly_rate")
    op.drop_column("project_labors", "fixed_value")
    op.drop_column("project_labors", "labor_type")
    op.alter_column("project_labors", "employee_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("project_labors_employee_id_fkey", "project_labors", type_="foreignkey")
    op.create_foreign_key(
        "project_labors_employee_id_fkey",
        "project_labors",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_project_labors_project_employee_competencia",
        "project_labors",
        ["project_id", "employee_id", "competencia"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_project_labors_project_employee_competencia", "project_labors", type_="unique")
    op.drop_constraint("project_labors_employee_id_fkey", "project_labors", type_="foreignkey")
    op.create_foreign_key(
        "project_labors_employee_id_fkey",
        "project_labors",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("project_labors", "employee_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("project_labors", sa.Column("labor_type", sa.String(length=20), nullable=False, server_default="CLT"))
    op.add_column("project_labors", sa.Column("fixed_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("project_labors", sa.Column("hourly_rate", sa.Numeric(14, 4), nullable=True))
    op.add_column("project_labors", sa.Column("hours_per_month", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_labors", sa.Column("monthly_cost", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.alter_column("project_labors", "labor_type", server_default=None)
    op.alter_column("project_labors", "monthly_cost", server_default=None)
