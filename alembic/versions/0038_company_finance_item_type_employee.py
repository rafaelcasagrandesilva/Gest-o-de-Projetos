"""company finance item type + employee link

Revision ID: 0038_company_finance_item_type_employee
Revises: 0037_add_employee_pix_key
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0038_company_finance_item_type_employee"
down_revision = "0037_add_employee_pix_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE company_financial_item_type AS ENUM ('MANUAL', 'COLABORADOR_MATRIZ')"
    )
    op.add_column(
        "company_financial_items",
        sa.Column(
            "item_type",
            sa.Enum("MANUAL", "COLABORADOR_MATRIZ", name="company_financial_item_type"),
            nullable=False,
            server_default="MANUAL",
        ),
    )
    op.add_column(
        "company_financial_items",
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "company_financial_items",
        sa.Column("percentual", sa.Numeric(6, 2), nullable=True),
    )
    op.create_index(
        "ix_company_financial_items_employee_id",
        "company_financial_items",
        ["employee_id"],
    )
    op.create_foreign_key(
        "fk_company_financial_items_employee_id",
        "company_financial_items",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_company_financial_items_employee_id", "company_financial_items", type_="foreignkey")
    op.drop_index("ix_company_financial_items_employee_id", table_name="company_financial_items")
    op.drop_column("company_financial_items", "percentual")
    op.drop_column("company_financial_items", "employee_id")
    op.drop_column("company_financial_items", "item_type")
    op.execute("DROP TYPE company_financial_item_type")

