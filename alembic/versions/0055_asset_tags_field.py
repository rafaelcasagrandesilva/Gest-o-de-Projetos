"""Ativos: campo tags (JSONB).

Revision ID: 0055_asset_tags_field
Revises: 0054_asset_size_field
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0055_asset_tags_field"
down_revision = "0054_asset_size_field"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("tags", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("assets", "tags")
