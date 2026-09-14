"""Custos Indiretos: "Rateio pela frota" como modo (NULL | LOCACAO | ADICIONAL) em bancos que já rodaram a 0137 booleana.

A 0137 foi reescrita (antes de publicada) para já criar `fleet_allocation` como VARCHAR(16) com o
modo. Bancos que chegaram a aplicar a versão BOOLEANA anterior ficaram com a coluna errada; esta
migration converte a coluna nesses bancos e não faz nada nos demais (verifica o tipo antes).

Modos, por ids explícitos (só itens `custo_fixo`):
- dc7e1444-0f65-41db-9f94-ca76f360cc98 — "Movida - Locação Frota" → LOCACAO (substitui o custo dos veículos)
- e0dcd25f-4d29-46d4-ab3d-76a8794fa3fb — "PORTO SEGURO CIA DE SEGUROS GERAIS (Seguro Frota)" → ADICIONAL (soma)

Revision ID: 0138_fleet_allocation_mode
Revises: 0137_fleet_allocation_flag
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0138_fleet_allocation_mode"
down_revision = "0137_fleet_allocation_flag"
branch_labels = None
depends_on = None

_CHECK = "ck_company_financial_items_fleet_allocation"
_MODES = (
    ("dc7e1444-0f65-41db-9f94-ca76f360cc98", "LOCACAO"),
    ("e0dcd25f-4d29-46d4-ab3d-76a8794fa3fb", "ADICIONAL"),
)


def _column_type(conn) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'company_financial_items' AND column_name = 'fleet_allocation'"
        )
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    if _column_type(conn) != "boolean":
        return  # banco já criado pela 0137 atual (VARCHAR) — nada a converter
    conn.execute(sa.text("ALTER TABLE company_financial_items ALTER COLUMN fleet_allocation DROP DEFAULT"))
    conn.execute(sa.text("ALTER TABLE company_financial_items ALTER COLUMN fleet_allocation DROP NOT NULL"))
    conn.execute(
        sa.text("ALTER TABLE company_financial_items ALTER COLUMN fleet_allocation TYPE VARCHAR(16) USING NULL")
    )
    for item_id, mode in _MODES:
        conn.execute(
            sa.text(
                "UPDATE company_financial_items SET fleet_allocation = :mode "
                "WHERE id = CAST(:id AS uuid) AND tipo = 'custo_fixo'"
            ),
            {"id": item_id, "mode": mode},
        )
    op.create_check_constraint(
        _CHECK,
        "company_financial_items",
        "fleet_allocation IS NULL OR fleet_allocation IN ('LOCACAO', 'ADICIONAL')",
    )


def downgrade() -> None:
    # A 0137 atual já define a coluna como VARCHAR com o modo: não há o que desfazer aqui.
    pass
