"""Contas a Pagar: tipo ANTECIPACAO_OPERACAO (obrigações de borderô).

Adiciona o valor `ANTECIPACAO_OPERACAO` ao enum `payable_snapshot_type`. Usado
exclusivamente pelas obrigações financeiras de uma operação de antecipação (deságio,
tarifas, repasse 7%), com ref_id = borderô. Isolado do tipo `ANTECIPACAO` (antecipação
individual de NF) para não interferir na reconciliação de snapshots. Exibido como
"Antecipação" na interface.

Revision ID: 0079_payable_type_antecipacao_operacao
Revises: 0078_advance_batch_sgc_number
"""

from __future__ import annotations

from alembic import op

revision = "0079_payable_type_antecipacao_operacao"
down_revision = "0078_advance_batch_sgc_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 12+: ADD VALUE é permitido dentro de transação (não é usado no mesmo
    # comando). IF NOT EXISTS torna a migração idempotente.
    op.execute("ALTER TYPE payable_snapshot_type ADD VALUE IF NOT EXISTS 'ANTECIPACAO_OPERACAO'")


def downgrade() -> None:
    # PostgreSQL não suporta remover um valor de enum; downgrade é no-op.
    # As linhas com esse tipo continuam legíveis; nenhuma ação segura de reversão.
    pass
