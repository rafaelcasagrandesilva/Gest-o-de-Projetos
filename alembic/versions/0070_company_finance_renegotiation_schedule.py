"""company finance: cronograma de renegociação (endividamento).

Adiciona três colunas em `company_financial_items` para registrar o cronograma
de uma renegociação parcelada:
- `renegotiation_agreement_date`: data em que o acordo foi fechado;
- `renegotiation_first_payment_date`: data do primeiro pagamento;
- `renegotiation_due_day`: dia recorrente de vencimento das parcelas (1–31).

Servem apenas para derivar a parcela esperada por competência (obrigatoriedade
automática de monitoramento). NÃO criam lançamento financeiro, conta a pagar
ou título com valor zero. Todas as colunas são NULLABLE — dados existentes
permanecem válidos.

Revision ID: 0070_company_finance_renegotiation_schedule
Revises: 0069_payable_snapshot_reconcile_permission
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0070_company_finance_renegotiation_schedule"
down_revision = "0069_payable_snapshot_reconcile_permission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_items",
        sa.Column("renegotiation_agreement_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "company_financial_items",
        sa.Column("renegotiation_first_payment_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "company_financial_items",
        sa.Column("renegotiation_due_day", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_financial_items", "renegotiation_due_day")
    op.drop_column("company_financial_items", "renegotiation_first_payment_date")
    op.drop_column("company_financial_items", "renegotiation_agreement_date")
