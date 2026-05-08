"""add projects.cost_center

Revision ID: 0044_project_cost_center
Revises: 0043_vehicle_soft_delete
Create Date: 2026-04-29

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0044_project_cost_center"
down_revision = "0043_vehicle_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("cost_center", sa.String(length=255), nullable=True),
    )
    op.create_index(op.f("ix_projects_cost_center"), "projects", ["cost_center"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_cost_center"), table_name="projects")
    op.drop_column("projects", "cost_center")
