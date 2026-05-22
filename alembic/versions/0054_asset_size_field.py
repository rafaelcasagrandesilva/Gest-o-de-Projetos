"""Ativos: campo size (EPI / vestimentas).

Revision ID: 0054_asset_size_field
Revises: 0053_asset_assignment_return_fields
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054_asset_size_field"
down_revision = "0053_asset_assignment_return_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("size", sa.String(length=32), nullable=True))
    op.create_index("ix_assets_size", "assets", ["size"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assets_size", table_name="assets")
    op.drop_column("assets", "size")
