"""company_finance: debt renegotiation fields

Revision ID: 0033_company_finance_debt_renegotiation
Revises: 0032_payable_snapshot_type_financial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_company_finance_debt_renegotiation"
down_revision = "0032_payable_snapshot_type_financial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'renegotiation_type') THEN
                CREATE TYPE renegotiation_type AS ENUM ('UNIQUE', 'INSTALLMENTS');
            END IF;
        END$$;
        """
    )

    op.add_column(
        "company_financial_items",
        sa.Column("has_legal_process", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "company_financial_items",
        sa.Column("has_renegotiation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("company_financial_items", sa.Column("renegotiated_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column(
        "company_financial_items",
        sa.Column("renegotiation_type", sa.Enum("UNIQUE", "INSTALLMENTS", name="renegotiation_type"), nullable=True),
    )
    op.add_column("company_financial_items", sa.Column("installment_count", sa.Integer(), nullable=True))
    op.add_column("company_financial_items", sa.Column("installment_value", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("company_financial_items", "installment_value")
    op.drop_column("company_financial_items", "installment_count")
    op.drop_column("company_financial_items", "renegotiation_type")
    op.drop_column("company_financial_items", "renegotiated_amount")
    op.drop_column("company_financial_items", "has_renegotiation")
    op.drop_column("company_financial_items", "has_legal_process")
    op.execute("DROP TYPE IF EXISTS renegotiation_type")

