"""Liquidação de NFs: prorrogação de vencimento e juros pagos.

- `advance_obligation_extensions`: prorrogações do vencimento de uma obrigação perante a
  instituição (append-only; a vigente é a última ativa). O vencimento da NF não muda.
- `advance_settlement_movements.interest_amount`: parte paga ACIMA do residual (juros), aceita
  quando a NF foi prorrogada ou é paga após o vencimento. `amount` continua sendo só o principal,
  então todos os totais de liquidado/residual existentes ficam idênticos.

Aditiva. downgrade remove a coluna e a tabela.

Revision ID: 0149_obligation_extension_interest
Revises: 0148_agenda_item_obligations
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0149_obligation_extension_interest"
down_revision = "0148_agenda_item_obligations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advance_obligation_extensions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_due", sa.Date(), nullable=True),
        sa.Column("new_due", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_item_id"], ["receivable_advance_batch_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_advance_obligation_extensions_batch_item_id", "advance_obligation_extensions", ["batch_item_id"]
    )
    op.add_column(
        "advance_settlement_movements",
        sa.Column("interest_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("advance_settlement_movements", "interest_amount")
    op.drop_index("ix_advance_obligation_extensions_batch_item_id", table_name="advance_obligation_extensions")
    op.drop_table("advance_obligation_extensions")
