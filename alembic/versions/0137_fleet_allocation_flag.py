"""company finance: modo fleet_allocation ("Rateio pela frota") nos Custos Indiretos.

Adiciona a coluna `fleet_allocation` VARCHAR(16) NULL em `company_financial_items`, com CHECK
`ck_company_financial_items_fleet_allocation` (NULL ou 'LOCACAO'/'ADICIONAL'). Três estados:
    - NULL        sem rateio pela frota (padrão) — o item segue como custo indireto.
    - 'LOCACAO'   "Fatura de locação da frota": a fatura SUBSTITUI o custo dos veículos e é
                  dividida entre os projetos pelo custo mensal dos veículos de cada centro de custo.
    - 'ADICIONAL' "Custo adicional da frota" (ex.: seguro): dividida do mesmo jeito e SOMADA ao
                  custo dos veículos.
O restante (parte não atribuída a projeto) continua como custo indireto. Só faz sentido em
tipo='custo_fixo' (Endividamento fica sempre NULL).

Carga de dados (confirmada pelo usuário) — por lista FECHADA de ids, nunca por nome:
    - dc7e1444-0f65-41db-9f94-ca76f360cc98  "Movida - Locação Frota"                             -> LOCACAO
    - e0dcd25f-4d29-46d4-ab3d-76a8794fa3fb  "PORTO SEGURO CIA DE SEGUROS GERAIS (Seguro Frota)"  -> ADICIONAL
Só marca se o item ainda for tipo='custo_fixo'. Um id ausente neste banco é ignorado.

Revision ID: 0137_fleet_allocation_flag
Revises: 0136_tax_regime
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0137_fleet_allocation_flag"
down_revision = "0136_tax_regime"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "company_financial_items"
CHECK_NAME = "ck_company_financial_items_fleet_allocation"

FLEET_ALLOCATION_SEED: tuple[tuple[str, str], ...] = (
    ("dc7e1444-0f65-41db-9f94-ca76f360cc98", "LOCACAO"),  # Movida - Locação Frota
    ("e0dcd25f-4d29-46d4-ab3d-76a8794fa3fb", "ADICIONAL"),  # PORTO SEGURO CIA DE SEGUROS GERAIS (Seguro Frota)
)


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("fleet_allocation", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        CHECK_NAME,
        TABLE,
        "fleet_allocation IS NULL OR fleet_allocation IN ('LOCACAO', 'ADICIONAL')",
    )

    conn = op.get_bind()
    for item_id, mode in FLEET_ALLOCATION_SEED:
        result = conn.execute(
            sa.text(
                f"UPDATE {TABLE} SET fleet_allocation = :mode "
                "WHERE tipo = 'custo_fixo' AND id = CAST(:id AS uuid)"
            ),
            {"mode": mode, "id": item_id},
        )
        logger.info("Rateio pela frota: %s -> %s (%s linha(s)).", item_id, mode, result.rowcount)


def downgrade() -> None:
    op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    op.drop_column(TABLE, "fleet_allocation")
