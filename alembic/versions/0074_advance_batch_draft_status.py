"""Operação de antecipação: status DRAFT (rascunho).

Adiciona o valor `DRAFT` ao enum `receivable_advance_batch_status`. A operação
passa a ser criada como rascunho; os efeitos financeiros (marcar NFs, gerar
Contas a Pagar, etc.) só ocorrem na confirmação.

Aditiva: operações existentes permanecem com seus status atuais (OPEN/SETTLED/
CANCELLED). Enum value não pode ser removido no downgrade (no-op).

Revision ID: 0074_advance_batch_draft_status
Revises: 0073_advance_institutions
"""

from __future__ import annotations

from alembic import op

revision = "0074_advance_batch_draft_status"
down_revision = "0073_advance_institutions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE receivable_advance_batch_status ADD VALUE IF NOT EXISTS 'DRAFT'")


def downgrade() -> None:
    # PostgreSQL não suporta remover valor de enum; downgrade é no-op.
    pass
