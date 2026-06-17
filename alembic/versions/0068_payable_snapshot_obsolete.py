"""payable snapshots: marcação de obsolescência (reconciliação).

Adiciona colunas para a funcionalidade "Reconciliar Snapshot" de Contas a Pagar:
sinalizar lançamentos automáticos cuja origem foi removida (colaborador, custo
fixo, alocação, antecipação) sem apagar histórico. NÃO altera valores, pagamentos,
estornos ou lançamentos manuais.

Colunas (todas aditivas e nullable / com default constante → metadata-only no PG):
- is_obsolete      BOOLEAN NOT NULL DEFAULT false
- obsolete_reason  TEXT NULL
- reconciled_at    TIMESTAMPTZ NULL
- reconciled_by    UUID NULL (FK users.id ON DELETE SET NULL)

Revision ID: 0068_payable_snapshot_obsolete
Revises: 0067_company_finance_monthly_required
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0068_payable_snapshot_obsolete"
down_revision = "0067_company_finance_monthly_required"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payable_snapshots",
        sa.Column("is_obsolete", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("payable_snapshots", sa.Column("obsolete_reason", sa.Text(), nullable=True))
    op.add_column(
        "payable_snapshots",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payable_snapshots",
        sa.Column("reconciled_by", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_payable_snapshots_reconciled_by_users",
        "payable_snapshots",
        "users",
        ["reconciled_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_payable_snapshots_is_obsolete", "payable_snapshots", ["is_obsolete"]
    )


def downgrade() -> None:
    op.drop_index("ix_payable_snapshots_is_obsolete", table_name="payable_snapshots")
    op.drop_constraint(
        "fk_payable_snapshots_reconciled_by_users", "payable_snapshots", type_="foreignkey"
    )
    op.drop_column("payable_snapshots", "reconciled_by")
    op.drop_column("payable_snapshots", "reconciled_at")
    op.drop_column("payable_snapshots", "obsolete_reason")
    op.drop_column("payable_snapshots", "is_obsolete")
