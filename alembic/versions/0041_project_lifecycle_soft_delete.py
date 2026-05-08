"""project lifecycle soft delete

Revision ID: 0041_project_lifecycle_soft_delete
Revises: 0040_receivable_manual_items
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0041_project_lifecycle_soft_delete"
down_revision = "0040_receivable_manual_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("projects", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_projects_is_active", "projects", ["is_active"])
    op.create_index("ix_projects_closed_at", "projects", ["closed_at"])
    op.create_index("ix_projects_deleted_at", "projects", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_projects_deleted_at", table_name="projects")
    op.drop_index("ix_projects_closed_at", table_name="projects")
    op.drop_index("ix_projects_is_active", table_name="projects")

    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "closed_at")
    op.drop_column("projects", "is_active")

