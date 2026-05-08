"""project closed/deleted timestamptz

Revision ID: 0042_project_closed_deleted_timestamptz
Revises: 0041_project_lifecycle_soft_delete
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_project_closed_deleted_timestamptz"
down_revision = "0041_project_lifecycle_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alguns bancos podem ter criado as colunas como timestamp sem timezone.
    # Converter para timestamptz mantendo o mesmo valor (assumindo UTC).
    op.alter_column(
        "projects",
        "closed_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        postgresql_using="closed_at AT TIME ZONE 'UTC'",
        existing_nullable=True,
    )
    op.alter_column(
        "projects",
        "deleted_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        postgresql_using="deleted_at AT TIME ZONE 'UTC'",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "projects",
        "deleted_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        postgresql_using="deleted_at::timestamp",
        existing_nullable=True,
    )
    op.alter_column(
        "projects",
        "closed_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        postgresql_using="closed_at::timestamp",
        existing_nullable=True,
    )

