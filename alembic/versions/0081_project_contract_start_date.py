"""Projetos: data de início do contrato + prazo total em meses (inteiro).

Adiciona `contract_start_date` (Date) e converte `contract_duration` de texto para
inteiro (prazo total em MESES). A data final do contrato é derivada (início + prazo)
e NÃO é armazenada — calculada dinamicamente na leitura. Puramente cadastral.

Revision ID: 0081_project_contract_start_date
Revises: 0080_project_contract_info
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0081_project_contract_start_date"
down_revision = "0080_project_contract_info"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("contract_start_date", sa.Date(), nullable=True))
    # Converte o prazo total de texto para inteiro (meses). Valores não numéricos ou
    # vazios viram NULL (a funcionalidade é recente; não há dados relevantes a preservar).
    op.alter_column(
        "projects",
        "contract_duration",
        existing_type=sa.String(length=120),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="NULLIF(regexp_replace(contract_duration, '[^0-9]', '', 'g'), '')::integer",
    )


def downgrade() -> None:
    op.alter_column(
        "projects",
        "contract_duration",
        existing_type=sa.Integer(),
        type_=sa.String(length=120),
        existing_nullable=True,
        postgresql_using="contract_duration::text",
    )
    op.drop_column("projects", "contract_start_date")
