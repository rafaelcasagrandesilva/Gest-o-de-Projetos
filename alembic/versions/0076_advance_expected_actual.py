"""Operação de antecipação: valor previsto x realizado.

Adiciona (genérico, para qualquer perfil que trabalhe com previsto/realizado):
- receivable_advance_batches.expected_amount  → valor previsto (ex.: Daycoval = soma
  dos antecipados informados por NF). Congelado na confirmação, nunca sobrescrito.
- receivable_advance_batches.actual_received_amount → valor efetivamente recebido,
  informado posteriormente pelo usuário (NULL até ser informado).

`received_amount` (já existente) continua sendo o valor que o Dashboard usa:
= previsto até o realizado ser informado; passa a = realizado depois.

Aditiva e nullable: operações existentes permanecem inalteradas.

Revision ID: 0076_advance_expected_actual
Revises: 0075_advance_lepta_basis_repasse
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0076_advance_expected_actual"
down_revision = "0075_advance_lepta_basis_repasse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_advance_batches",
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "receivable_advance_batches",
        sa.Column("actual_received_amount", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receivable_advance_batches", "actual_received_amount")
    op.drop_column("receivable_advance_batches", "expected_amount")
