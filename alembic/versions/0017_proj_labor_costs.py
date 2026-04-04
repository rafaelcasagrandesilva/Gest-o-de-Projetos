"""Custos mensais versionados em project_labors (overrides por competência e cenário).

Revision ID: 0017_proj_labor_costs (≤32 chars para alembic_version.version_num)
Revises: 0016_scenario_columns_ensure
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_proj_labor_costs"
down_revision = "0016_scenario_columns_ensure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_labors", sa.Column("cost_salary_base", sa.Numeric(14, 2), nullable=True))
    op.add_column("project_labors", sa.Column("cost_additional_costs", sa.Numeric(14, 2), nullable=True))
    op.add_column("project_labors", sa.Column("cost_extra_hours_50", sa.Numeric(10, 2), nullable=True))
    op.add_column("project_labors", sa.Column("cost_extra_hours_70", sa.Numeric(10, 2), nullable=True))
    op.add_column("project_labors", sa.Column("cost_extra_hours_100", sa.Numeric(10, 2), nullable=True))
    op.add_column("project_labors", sa.Column("cost_pj_hours_per_month", sa.Numeric(10, 2), nullable=True))
    op.add_column("project_labors", sa.Column("cost_pj_additional_cost", sa.Numeric(14, 2), nullable=True))
    op.add_column("project_labors", sa.Column("cost_total_override", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("project_labors", "cost_total_override")
    op.drop_column("project_labors", "cost_pj_additional_cost")
    op.drop_column("project_labors", "cost_pj_hours_per_month")
    op.drop_column("project_labors", "cost_extra_hours_100")
    op.drop_column("project_labors", "cost_extra_hours_70")
    op.drop_column("project_labors", "cost_extra_hours_50")
    op.drop_column("project_labors", "cost_additional_costs")
    op.drop_column("project_labors", "cost_salary_base")
