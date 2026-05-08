"""payable_snapshot_type: add FINANCIAL

Revision ID: 0032_payable_snapshot_type_financial
Revises: 0031_receivable_status_recebida
"""

from __future__ import annotations

from alembic import op

revision = "0032_payable_snapshot_type_financial"
down_revision = "0031_receivable_status_recebida"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL enum: adiciona novo valor (sem reordenação).
    op.execute("ALTER TYPE payable_snapshot_type ADD VALUE IF NOT EXISTS 'FINANCIAL'")


def downgrade() -> None:
    # Não é trivial remover valor de enum em Postgres sem recriar tipo.
    raise NotImplementedError("Downgrade não suportado para alteração de enum.")

