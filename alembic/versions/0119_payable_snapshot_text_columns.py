"""`payable_snapshots.name` e `.item_description`: varchar(255) → TEXT.

Correção de um bug BLOQUEANTE: a geração do Contas a Pagar de setembro/2026 abortava com
`StringDataRightTruncationError` e a tela ficava zerada (R$ 0,00), sem conseguir carregar.

Causa: `payment_variable_components.note` é TEXT (sem limite) e a sincronização o copia para
`payable_snapshots.item_description`, que era varchar(255). Uma nota de 286 caracteres — o
detalhamento de uma ajuda de custo — estourava o limite e derrubava a geração do mês INTEIRO,
não só aquela linha.

`name` entra junto porque sofre da mesma aritmética: ele é a concatenação de
`employees.full_name` (que já é varchar(255)) com o rótulo do componente (" — Salário Base PJ").
Basta um nome longo para o resultado passar de 255. Hoje o maior nome tem 38 caracteres, então
o problema ainda não apareceu — esta migration o remove antes que apareça.

As duas colunas são texto de EXIBIÇÃO (nome do título e subtítulo cinza no CAP), sem índice e
sem participar de chave. Em PostgreSQL `varchar(n)` → `text` não reescreve a tabela e não há
diferença de desempenho entre os dois tipos.

Reversível: o downgrade volta para varchar(255), truncando o que exceder — por isso ele avisa
quantas linhas serão truncadas antes de fazê-lo.

Revision ID: 0119_payable_snapshot_text_columns
Revises: 0118_drop_legal_case_person_export
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0119_payable_snapshot_text_columns"
down_revision = "0118_drop_legal_case_person_export"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_COLUNAS = ("name", "item_description")


def upgrade() -> None:
    for coluna in _COLUNAS:
        op.alter_column(
            "payable_snapshots",
            coluna,
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=(coluna != "name"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    for coluna in _COLUNAS:
        excedentes = conn.execute(
            sa.text(
                f"select count(*) from payable_snapshots where length({coluna}) > 255"  # noqa: S608
            )
        ).scalar_one()
        if excedentes:
            # Voltar ao varchar(255) PERDE conteúdo — o downgrade avisa em vez de falhar
            # calado no meio da reversão.
            logger.warning(
                "downgrade 0119: %d linha(s) terão %s truncado em 255 caracteres",
                excedentes,
                coluna,
            )
            conn.execute(
                sa.text(
                    f"update payable_snapshots set {coluna} = left({coluna}, 255) "  # noqa: S608
                    f"where length({coluna}) > 255"
                )
            )
        op.alter_column(
            "payable_snapshots",
            coluna,
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=(coluna != "name"),
        )
