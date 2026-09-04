"""faturamento: escolher, por lançamento, entre o valor manual e a soma das NFs.

Adiciona `use_nf_amount` em `revenues`.

O faturamento é digitado manualmente por cada gestor e às vezes fica defasado em relação às
NFs efetivamente emitidas. A conferência feita em 04/09/2026 mostrou que Treinamentos bate
centavo a centavo todo mês, Subterrâneo erra por pouco e Fiscalização AT diverge muito (julho:
R$ 630.000,00 manual contra R$ 1.056.491,37 em NF) — ou seja, a confiabilidade varia por
projeto E por mês. Por isso a escolha é POR LANÇAMENTO, e não uma chave global ou por projeto:
o gestor pode adotar a soma das NFs num mês e manter o valor manual no seguinte.

O valor manual (`amount`) NUNCA é sobrescrito — permanece como o original informado. A flag só
diz qual dos dois o cálculo deve usar, de modo que desmarcar devolve exatamente o número
anterior.

`has_retention` continua no lançamento manual (a NF não tem esse conceito); o que muda quando a
flag está ligada é a BASE dos 10%, que passa a ser a soma das NFs.

Índice único parcial: no máximo UMA linha marcada por projeto+competência+cenário. Hoje só
existe uma linha por grupo, mas a unique constraint da tabela inclui `description` e portanto
permitiria duas — e duas linhas marcadas no mesmo mês fariam a soma das NFs entrar em dobro na
receita.

Exclusivamente ADITIVA — nasce `false` em todos os registros, preservando o comportamento atual.

Revision ID: 0124_revenue_use_nf_amount
Revises: 0123_debt_legal_person_link
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0124_revenue_use_nf_amount"
down_revision = "0123_debt_legal_person_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "revenues",
        sa.Column("use_nf_amount", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "uq_revenue_single_nf_source_per_competencia",
        "revenues",
        ["project_id", "competencia", "scenario"],
        unique=True,
        postgresql_where=sa.text("use_nf_amount"),
    )


def downgrade() -> None:
    op.drop_index("uq_revenue_single_nf_source_per_competencia", table_name="revenues")
    op.drop_column("revenues", "use_nf_amount")
