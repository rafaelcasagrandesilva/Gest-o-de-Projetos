"""Folha real mensal CLT (complementar; não altera custo gerencial).

Revision ID: 0056_employee_monthly_payroll_overrides
Revises: 0055_asset_tags_field
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056_employee_monthly_payroll_overrides"
down_revision = "0055_asset_tags_field"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_monthly_payroll_overrides",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("competence_month", sa.String(length=7), nullable=False),
        sa.Column("net_salary_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("vr_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_id",
            "competence_month",
            name="uq_employee_monthly_payroll_emp_comp",
        ),
    )
    op.create_index(
        "ix_employee_monthly_payroll_overrides_employee_id",
        "employee_monthly_payroll_overrides",
        ["employee_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_employee_monthly_payroll_overrides_employee_id",
        table_name="employee_monthly_payroll_overrides",
    )
    op.drop_table("employee_monthly_payroll_overrides")
