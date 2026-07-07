"""Ciclo de vida de cadastros mestres: is_active + start_date + end_date.

Padroniza o ciclo de vida (Ativo/Inativo + datas de início/encerramento) nos
cadastros mestres:
  - employees: + start_date, + end_date (is_active já existe)
  - vehicles:  + start_date, + end_date (is_active já existe)
  - company_financial_items (Custos Fixos + Endividamento): + is_active, + start_date, + end_date

Preservação de dados (100%): apenas `add_column`. Registros existentes ficam com
is_active=true (server_default) e datas NULL — não inventamos data de início histórica.
Nenhum dado é alterado ou removido.

Revision ID: 0083_master_entity_lifecycle
Revises: 0082_project_documents
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0083_master_entity_lifecycle"
down_revision = "0082_project_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Colaboradores — Admissão (start_date) / Desligamento (end_date). is_active já existe.
    op.add_column("employees", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("end_date", sa.Date(), nullable=True))

    # Veículos — Entrada (start_date) / Saída (end_date). is_active já existe.
    op.add_column("vehicles", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("vehicles", sa.Column("end_date", sa.Date(), nullable=True))

    # Custos Fixos / Endividamento — Status + Início (start_date) / Encerramento (end_date).
    # is_active com server_default=true garante que os itens existentes permaneçam ATIVOS.
    op.add_column(
        "company_financial_items",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("company_financial_items", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("company_financial_items", sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("company_financial_items", "end_date")
    op.drop_column("company_financial_items", "start_date")
    op.drop_column("company_financial_items", "is_active")

    op.drop_column("vehicles", "end_date")
    op.drop_column("vehicles", "start_date")

    op.drop_column("employees", "end_date")
    op.drop_column("employees", "start_date")
