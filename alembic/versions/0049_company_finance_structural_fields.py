"""Company finance: add editable structural fields.

Revision ID: 0049_company_finance_structural_fields
Revises: 0048_payable_snapshot_type_endividamento
Create Date: 2026-05-19

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0049_company_finance_structural_fields"
down_revision = "0048_payable_snapshot_type_endividamento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_financial_items", sa.Column("category", sa.String(length=120), nullable=True))
    op.add_column("company_financial_items", sa.Column("cost_center", sa.String(length=255), nullable=True))
    op.add_column("company_financial_items", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("company_financial_items", sa.Column("recurrence", sa.String(length=32), nullable=True))
    op.execute(
        """
        UPDATE company_financial_items
           SET category = CASE WHEN tipo = 'endividamento' THEN 'Endividamento' ELSE 'Custos diversos' END,
               cost_center = CASE WHEN tipo = 'endividamento' THEN 'Financeiro' ELSE 'Administrativo' END,
               recurrence = CASE WHEN tipo = 'endividamento' THEN 'INSTALLMENTS' ELSE 'MONTHLY' END
         WHERE category IS NULL
            OR cost_center IS NULL
            OR recurrence IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("company_financial_items", "recurrence")
    op.drop_column("company_financial_items", "description")
    op.drop_column("company_financial_items", "cost_center")
    op.drop_column("company_financial_items", "category")
