"""Ativos: estado físico, purchase_value, soft delete em filhos.

Revision ID: 0052_assets_refinements
Revises: 0051_assets_management_module
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "0052_assets_refinements"
down_revision = "0051_assets_management_module"
branch_labels = None
depends_on = None

PHYSICAL_CONDITION = ("NEW", "GOOD", "FAIR", "DAMAGED")


def upgrade() -> None:
    sa.Enum(*PHYSICAL_CONDITION, name="asset_physical_condition").create(op.get_bind(), checkfirst=True)
    physical = PG_ENUM(*PHYSICAL_CONDITION, name="asset_physical_condition", create_type=False)

    op.add_column("assets", sa.Column("physical_condition", physical, nullable=True))
    op.alter_column(
        "assets",
        "acquisition_value",
        new_column_name="purchase_value",
        existing_type=sa.Numeric(14, 2),
        type_=sa.Numeric(12, 2),
        existing_nullable=True,
    )

    for table in ("asset_assignments", "asset_inspections", "asset_attachments"):
        op.add_column(
            table,
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_asset_attachments_deleted_at", table_name="asset_attachments")
    op.drop_index("ix_asset_inspections_deleted_at", table_name="asset_inspections")
    op.drop_index("ix_asset_assignments_deleted_at", table_name="asset_assignments")
    op.drop_column("asset_attachments", "deleted_at")
    op.drop_column("asset_inspections", "deleted_at")
    op.drop_column("asset_assignments", "deleted_at")
    op.alter_column(
        "assets",
        "purchase_value",
        new_column_name="acquisition_value",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(14, 2),
        existing_nullable=True,
    )
    op.drop_column("assets", "physical_condition")
    sa.Enum(name="asset_physical_condition").drop(op.get_bind(), checkfirst=True)
