"""Modelos de importação configurável — contas a pagar.

Revision ID: 0057_payable_import_templates
Revises: 0056_employee_monthly_payroll_overrides
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0057_payable_import_templates"
down_revision = "0056_employee_monthly_payroll_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payable_import_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("header_row", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_payable_import_template_user_name"),
    )
    op.create_index(
        "ix_payable_import_templates_user_id",
        "payable_import_templates",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_payable_import_templates_user_id", table_name="payable_import_templates")
    op.drop_table("payable_import_templates")
