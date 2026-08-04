"""Cronograma Financeiro Personalizado — Fase 2: sequência da parcela. ADITIVA.

Adiciona identidade estável da PARCELA dentro do cronograma:

- `company_financial_payments.+ schedule_seq INTEGER NULL`
  - Preenchido apenas em lançamentos do Modo 2 (cronograma); NULL em todos os legados e nos
    lançamentos comuns de Custos Fixos/Endividamento.
  - É a chave que permite REGERAR o cronograma por faixas preservando as parcelas já pagas:
    ao reexpandir, casamos a parcela `seq` com o lançamento existente (mesmo sem `id`), então
    parcelas pagas são mantidas intactas e apenas as futuras (abertas) são atualizadas.

Puramente ADITIVA e reversível: coluna nula, sem backfill, sem tocar dados/tipos/títulos do CAP.
Nada muda para Custos Fixos nem para a dívida legada (todos ficam com schedule_seq NULL).

Revision ID: 0104_payment_schedule_seq
Revises: 0103_debt_custom_schedule_flag
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0104_payment_schedule_seq"
down_revision = "0103_debt_custom_schedule_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_payments",
        sa.Column("schedule_seq", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_financial_payments", "schedule_seq")
