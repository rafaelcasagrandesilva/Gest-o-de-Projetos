"""Devolução: returned_to, returned_condition, return_notes em asset_assignments.

Revision ID: 0053_asset_assignment_return_fields
Revises: 0052_assets_refinements
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0053_asset_assignment_return_fields"
down_revision = "0052_assets_refinements"
branch_labels = None
depends_on = None

PHYSICAL = ("NEW", "GOOD", "FAIR", "DAMAGED")


def upgrade() -> None:
    physical = PG_ENUM(*PHYSICAL, name="asset_physical_condition", create_type=False)

    op.alter_column(
        "asset_assignments",
        "return_received_by_employee_id",
        new_column_name="returned_to_employee_id",
        existing_type=PG_UUID(as_uuid=True),
        existing_nullable=True,
    )
    op.add_column(
        "asset_assignments",
        sa.Column("returned_condition", physical, nullable=True),
    )
    op.add_column(
        "asset_assignments",
        sa.Column("return_notes", sa.Text(), nullable=True),
    )

    # Backfill: condição a partir do ativo quando já houve devolução.
    op.execute(
        """
        UPDATE asset_assignments aa
           SET returned_condition = a.physical_condition
          FROM assets a
         WHERE aa.asset_id = a.id
           AND aa.return_date IS NOT NULL
           AND aa.returned_condition IS NULL
           AND a.physical_condition IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("asset_assignments", "return_notes")
    op.drop_column("asset_assignments", "returned_condition")
    op.alter_column(
        "asset_assignments",
        "returned_to_employee_id",
        new_column_name="return_received_by_employee_id",
        existing_type=PG_UUID(as_uuid=True),
        existing_nullable=True,
    )
