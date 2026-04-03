"""company financial items: endividamento e custos fixos corporativos

Revision ID: 0012_company_financial_items
Revises: 0011_vehicle_monthly_cost
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0012_company_financial_items"
down_revision = "0011_vehicle_monthly_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_financial_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("valor_referencia", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_company_financial_items_tipo", "company_financial_items", ["tipo"], unique=False)

    op.create_table(
        "company_financial_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_financial_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint("item_id", "competencia", name="uq_company_financial_payment_month"),
    )
    op.create_index("ix_company_financial_payments_item_id", "company_financial_payments", ["item_id"], unique=False)
    op.create_index(
        "ix_company_financial_payments_competencia", "company_financial_payments", ["competencia"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_company_financial_payments_competencia", table_name="company_financial_payments")
    op.drop_index("ix_company_financial_payments_item_id", table_name="company_financial_payments")
    op.drop_table("company_financial_payments")
    op.drop_index("ix_company_financial_items_tipo", table_name="company_financial_items")
    op.drop_table("company_financial_items")
