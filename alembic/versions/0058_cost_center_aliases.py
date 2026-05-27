"""Aliases DE-PARA para centros de custo (importação financeira).

Revision ID: 0058_cost_center_aliases
Revises: 0057_payable_import_templates
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0058_cost_center_aliases"
down_revision = "0057_payable_import_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_center_aliases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("alias_name", sa.String(length=255), nullable=False),
        sa.Column("alias_name_normalized", sa.String(length=255), nullable=False),
        sa.Column("target_cost_center", sa.String(length=255), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias_name_normalized", name="uq_cost_center_alias_normalized"),
    )
    op.create_index(
        "ix_cost_center_aliases_target_cost_center",
        "cost_center_aliases",
        ["target_cost_center"],
    )
    op.create_index(
        "ix_cost_center_aliases_created_by_user_id",
        "cost_center_aliases",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_center_aliases_created_by_user_id", table_name="cost_center_aliases")
    op.drop_index("ix_cost_center_aliases_target_cost_center", table_name="cost_center_aliases")
    op.drop_table("cost_center_aliases")
