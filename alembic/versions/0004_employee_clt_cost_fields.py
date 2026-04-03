"""employee CLT cost fields + PJ hours

Revision ID: 0004_employee_clt_cost
Revises: 0003_settings_operational
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0004_employee_clt_cost"
down_revision = "0003_settings_operational"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("has_periculosidade", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "employees",
        sa.Column("has_adicional_dirigida", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "employees",
        sa.Column("extra_hours_50", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "employees",
        sa.Column("extra_hours_70", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "employees",
        sa.Column("extra_hours_100", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column("employees", sa.Column("pj_hours_per_month", sa.Numeric(10, 2), nullable=True))
    op.alter_column("employees", "has_periculosidade", server_default=None)
    op.alter_column("employees", "has_adicional_dirigida", server_default=None)
    op.alter_column("employees", "extra_hours_50", server_default=None)
    op.alter_column("employees", "extra_hours_70", server_default=None)
    op.alter_column("employees", "extra_hours_100", server_default=None)


def downgrade() -> None:
    op.drop_column("employees", "pj_hours_per_month")
    op.drop_column("employees", "extra_hours_100")
    op.drop_column("employees", "extra_hours_70")
    op.drop_column("employees", "extra_hours_50")
    op.drop_column("employees", "has_adicional_dirigida")
    op.drop_column("employees", "has_periculosidade")
