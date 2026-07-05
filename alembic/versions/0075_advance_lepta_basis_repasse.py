"""Fluxo Lepta: base de antecipação por NF + repasse 7%.

Adiciona:
- receivable_advance_batch_items.advance_basis (BRUTO|LIQUIDO|LIQUIDO_MENOS_10|…)
- receivable_advance_batch_items.advanced_amount (valor antecipado congelado da NF)
- receivable_advance_batches.repasse_enabled (checkbox "Reter 7%")
- receivable_advance_batches.repasse_amount (valor do repasse, congelado na confirmação)

Aditiva e nullable: operações/itens existentes permanecem inalterados.

Revision ID: 0075_advance_lepta_basis_repasse
Revises: 0074_advance_batch_draft_status
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0075_advance_lepta_basis_repasse"
down_revision = "0074_advance_batch_draft_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_advance_batch_items",
        sa.Column("advance_basis", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "receivable_advance_batch_items",
        sa.Column("advanced_amount", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "receivable_advance_batches",
        sa.Column("repasse_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "receivable_advance_batches",
        sa.Column("repasse_amount", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receivable_advance_batches", "repasse_amount")
    op.drop_column("receivable_advance_batches", "repasse_enabled")
    op.drop_column("receivable_advance_batch_items", "advanced_amount")
    op.drop_column("receivable_advance_batch_items", "advance_basis")
