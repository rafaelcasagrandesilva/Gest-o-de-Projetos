"""Projetos: informações contratuais + aditivos (relação 1-N).

Adiciona campos cadastrais de contrato/comprador/gestor em `projects` e cria a
tabela normalizada `project_contract_additives` (N aditivos por projeto). Puramente
cadastral — não altera nenhuma regra financeira, dashboard, snapshot ou indicador.
Projetos existentes continuam funcionando com os novos campos vazios.

Revision ID: 0080_project_contract_info
Revises: 0079_payable_type_antecipacao_operacao
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0080_project_contract_info"
down_revision = "0079_payable_type_antecipacao_operacao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Campos contratuais no projeto (todos nullable — projetos atuais ficam vazios).
    op.add_column("projects", sa.Column("contract_number", sa.String(length=120), nullable=True))
    op.add_column("projects", sa.Column("contract_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("projects", sa.Column("contract_duration", sa.String(length=120), nullable=True))
    op.add_column("projects", sa.Column("buyer_name", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("buyer_phone", sa.String(length=50), nullable=True))
    op.add_column("projects", sa.Column("buyer_email", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("manager_name", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("manager_phone", sa.String(length=50), nullable=True))
    op.add_column("projects", sa.Column("manager_email", sa.String(length=255), nullable=True))

    op.create_table(
        "project_contract_additives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("additive_date", sa.Date(), nullable=True),
        sa.Column("additive_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("additive_duration", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_project_contract_additives_project_id",
        "project_contract_additives",
        ["project_id"],
    )
    op.create_foreign_key(
        "fk_project_contract_additive_project",
        "project_contract_additives",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_project_contract_additive_project", "project_contract_additives", type_="foreignkey"
    )
    op.drop_index("ix_project_contract_additives_project_id", table_name="project_contract_additives")
    op.drop_table("project_contract_additives")
    for col in (
        "manager_email",
        "manager_phone",
        "manager_name",
        "buyer_email",
        "buyer_phone",
        "buyer_name",
        "contract_duration",
        "contract_value",
        "contract_number",
    ):
        op.drop_column("projects", col)
