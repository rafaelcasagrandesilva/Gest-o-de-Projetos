"""employee pj_additional_cost

Revision ID: 0005_pj_additional_cost
Revises: 0004_employee_clt_cost
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005_pj_additional_cost"
down_revision = "0004_employee_clt_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("pj_additional_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )
    op.alter_column("employees", "pj_additional_cost", server_default=None)


def downgrade() -> None:
    op.drop_column("employees", "pj_additional_cost")
