"""Descrição própria do item (Endividamento) — coluna `item_description`.

Normaliza o cadastro de Endividamento: além do vínculo opcional com colaborador
(`employee_id`, já existente desde 0038), o item passa a ter uma descrição própria
(ex.: "Acordo de Remuneração", "Acerto de Mútuos"), separada do `nome`. O nome do item
passa a ser composto automaticamente ("<colaborador> - <descrição>", ou só a descrição).

A mesma coluna é adicionada ao snapshot de Contas a Pagar para permitir exibir Credor
(`name`) e Descrição (`item_description`) separadamente. O nome `item_description` é
genérico de propósito — poderá ser reaproveitado por outros tipos de lançamento no futuro.

Preservação de dados (100%): apenas `add_column` (nullable). Nenhuma linha existente é
alterada e NENHUM UPDATE em massa é feito. Registros legados ficam com
`item_description = NULL` e continuam exibidos exatamente como hoje (via `nome`).

Revision ID: 0086_endividamento_item_description
Revises: 0085_employee_cost_center
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0086_endividamento_item_description"
down_revision = "0085_employee_cost_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_items",
        sa.Column("item_description", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "payable_snapshots",
        sa.Column("item_description", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payable_snapshots", "item_description")
    op.drop_column("company_financial_items", "item_description")
