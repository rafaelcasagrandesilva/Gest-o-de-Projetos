"""endividamento: "Entra no Resultado da Empresa" por dívida.

Coluna nova `company_financial_items.include_in_company_result` (padrão TRUE = tudo continua
como estava). Dívida desmarcada não conta em "Dívidas pagas" do Resultado da Empresa
(Indicadores) — nem pelo CAP nem pelas retiradas do Repasse. Não afeta CAP, Endividamento
nem o Jurídico.

Pedido do Rafael (2026-11-05): tirar o Rogério Ifran da conta das dívidas — desmarcado aqui
pelo id do item (o banco de teste é clone da produção). Depois disso se muda pela tela.

Revision ID: 0161_debt_include_in_company_result
Revises: 0160_advance_batch_attachments
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0161_debt_include_in_company_result"
down_revision = "0160_advance_batch_attachments"
branch_labels = None
depends_on = None

# "Rogerio Luiz Ifran Ratier" (endividamento).
ROGERIO_IFRAN_ITEM_ID = "973092c7-603f-4f79-8466-c3b93acc10ed"


def upgrade() -> None:
    op.add_column(
        "company_financial_items",
        sa.Column("include_in_company_result", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        sa.text(
            "UPDATE company_financial_items SET include_in_company_result = false "
            "WHERE id = CAST(:id AS uuid) AND tipo = 'endividamento'"
        ).bindparams(id=ROGERIO_IFRAN_ITEM_ID)
    )


def downgrade() -> None:
    op.drop_column("company_financial_items", "include_in_company_result")
