"""company finance: "Entra no projeto como" (project_cost_group) nos Custos Indiretos.

Adiciona a coluna `project_cost_group` VARCHAR(16) NULL em `company_financial_items`, com CHECK
`ck_company_financial_items_project_cost_group` (NULL ou 'MAO_DE_OBRA'/'VEICULOS'/'SISTEMAS'/'FIXOS').
Define em qual custo RAIZ do projeto um item de custo fixo com centro de custo = PROJETO soma
(Dashboard Operacional / Resultado da Empresa), em vez de uma linha separada. Só faz sentido
quando o centro de custo é um projeto. NULL = Fixos operacionais (padrão). Endividamento fica
sempre NULL.

Carga de dados — por lista FECHADA de ids, nunca por nome (todos os itens custo_fixo com centro
de custo = projeto existentes no levantamento):
    - 6dd0f06d-70ea-41b6-9978-cfa254747c5f  "TICKET SOLUÇÕES - FISCALIZAÇÃO AT"                            -> VEICULOS
    - 86247387-638f-4e9d-84d5-0a0dd5a1a057  "TICKET SOLUÇÕES - SUBTERRÂNEO"                                -> VEICULOS
    - 89e58417-578b-4fa4-ad18-27c3952f1021  "TICKET SOLUÇÕES - LUMINOTECNICO"                              -> VEICULOS
    - bd65201b-4888-497b-827c-05bad7a6cb09  "SUL AMERICA CIA SEGURO SAUDE - FISCALIZAÇAO AT"               -> MAO_DE_OBRA
    - 84298f83-f6ea-4f60-b40d-6db927a5f86f  "SUL AMERICA CIA SEGURO SAUDE - REDE SUBTERRANEA"              -> MAO_DE_OBRA
    - 005e6141-db8e-493d-88fc-8eea0530ce12  "SUL AMERICA CIA SEGURO SAUDE -  Censo de IP e Uso Mútuo - MT" -> MAO_DE_OBRA
Só marca se o item ainda for tipo='custo_fixo'. Um id ausente neste banco é ignorado.

Revision ID: 0139_project_cost_group
Revises: 0138_fleet_allocation_mode
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0139_project_cost_group"
down_revision = "0138_fleet_allocation_mode"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "company_financial_items"
CHECK_NAME = "ck_company_financial_items_project_cost_group"

PROJECT_COST_GROUP_SEED: tuple[tuple[str, str], ...] = (
    ("6dd0f06d-70ea-41b6-9978-cfa254747c5f", "VEICULOS"),  # TICKET SOLUÇÕES - FISCALIZAÇÃO AT
    ("86247387-638f-4e9d-84d5-0a0dd5a1a057", "VEICULOS"),  # TICKET SOLUÇÕES - SUBTERRÂNEO
    ("89e58417-578b-4fa4-ad18-27c3952f1021", "VEICULOS"),  # TICKET SOLUÇÕES - LUMINOTECNICO
    ("bd65201b-4888-497b-827c-05bad7a6cb09", "MAO_DE_OBRA"),  # SUL AMERICA CIA SEGURO SAUDE - FISCALIZAÇAO AT
    ("84298f83-f6ea-4f60-b40d-6db927a5f86f", "MAO_DE_OBRA"),  # SUL AMERICA CIA SEGURO SAUDE - REDE SUBTERRANEA
    ("005e6141-db8e-493d-88fc-8eea0530ce12", "MAO_DE_OBRA"),  # SUL AMERICA CIA SEGURO SAUDE -  Censo de IP e Uso Mútuo - MT
)


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("project_cost_group", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        CHECK_NAME,
        TABLE,
        "project_cost_group IS NULL OR project_cost_group IN ('MAO_DE_OBRA', 'VEICULOS', 'SISTEMAS', 'FIXOS')",
    )

    conn = op.get_bind()
    for item_id, group in PROJECT_COST_GROUP_SEED:
        result = conn.execute(
            sa.text(
                f"UPDATE {TABLE} SET project_cost_group = :group "
                "WHERE tipo = 'custo_fixo' AND id = CAST(:id AS uuid)"
            ),
            {"group": group, "id": item_id},
        )
        logger.info("Entra no projeto como: %s -> %s (%s linha(s)).", item_id, group, result.rowcount)


def downgrade() -> None:
    op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    op.drop_column(TABLE, "project_cost_group")
