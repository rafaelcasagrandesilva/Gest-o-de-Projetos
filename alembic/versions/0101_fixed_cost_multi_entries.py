"""Custos Fixos — MÚLTIPLOS LANÇAMENTOS por competência (Fase 1: grade). ADITIVA.

Evolui `company_financial_payments` (a "grade mensal") de EXATAMENTE um valor por
(item, competência) para N LANÇAMENTOS na mesma competência. Cada lançamento passa a ter
vencimento e descrição próprios e, na Fase 2, gera um título independente no Contas a Pagar.

Mudanças (todas aditivas / sem perda de dado):
- `+ due_date DATE NULL`   → vencimento do lançamento (governa o due_date do CAP);
- `+ descricao VARCHAR(255) NULL` → descrição livre (ex.: "1ª quinzena", "NF 45872");
- DROP da unicidade `uq_company_financial_payment_month` (item_id, competencia) → permite N.

Backfill do vencimento (preserva o que já existe no CAP): para cada lançamento legado,
`due_date` = vencimento do título corporativo correspondente no Contas a Pagar
(FIXED_COST/ENDIVIDAMENTO/FINANCIAL, project_id nulo, mesmo item e mês) quando existir;
senão, dia 10 da competência (consistente com `_default_due_date(comp, day=10)`). Assim
nenhum vencimento já gravado muda.

Genérico de propósito (serve qualquer item de Custo Fixo). O comportamento multi-lançamento
é ligado na Fase 2 (backend); esta migração NÃO altera comportamento: cada mês continua com
um único lançamento, agora com vencimento/descrição preenchidos.

Revision ID: 0101_fixed_cost_multi_entries
Revises: 0100_payment_variable_components
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0101_fixed_cost_multi_entries"
down_revision = "0100_payment_variable_components"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_payments",
        sa.Column("due_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "company_financial_payments",
        sa.Column("descricao", sa.String(length=255), nullable=True),
    )

    # Backfill do vencimento: copia do título CAP correspondente; senão dia 10 da competência.
    op.execute(
        """
        UPDATE company_financial_payments AS cfp
        SET due_date = COALESCE(
            (
                SELECT MIN(ps.due_date)
                FROM payable_snapshots AS ps
                WHERE ps.ref_id = cfp.item_id
                  AND ps.month = cfp.competencia
                  AND ps.project_id IS NULL
                  AND ps.type::text IN ('FIXED_COST', 'ENDIVIDAMENTO', 'FINANCIAL')
            ),
            make_date(
                EXTRACT(YEAR FROM cfp.competencia)::int,
                EXTRACT(MONTH FROM cfp.competencia)::int,
                10
            )
        )
        WHERE cfp.due_date IS NULL
        """
    )

    # A partir daqui, N lançamentos por competência são permitidos.
    op.drop_constraint(
        "uq_company_financial_payment_month",
        "company_financial_payments",
        type_="unique",
    )


def downgrade() -> None:
    # Recria a unicidade (só é possível se não houver >1 lançamento por (item, competência)).
    op.create_unique_constraint(
        "uq_company_financial_payment_month",
        "company_financial_payments",
        ["item_id", "competencia"],
    )
    op.drop_column("company_financial_payments", "descricao")
    op.drop_column("company_financial_payments", "due_date")
