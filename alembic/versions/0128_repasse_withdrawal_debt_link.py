"""Retirada de Repasse aponta para a dívida que ela abate.

O Ledger de Repasse já registrava o DESTINO da retirada (`withdrawal_purpose = DEBT_REDUCTION`),
mas não QUAL dívida — o comentário do modelo previa esta integração ("permitir, no futuro,
localizar as retiradas de DEBT_REDUCTION e integrá-las ao módulo de Endividamento sem parsing de
texto"). Esta coluna é esse elo.

Com ela, a retirada passa a contar como PAGAMENTO da dívida na competência em que ocorreu, na
Evolução da dívida. **Sem gerar título no Contas a Pagar**: o dinheiro nunca passa pelo caixa da
empresa — já estava retido na instituição, dentro do repasse das antecipações. Lançar um título
seria prometer um desembolso que não vai existir.

ON DELETE SET NULL: apagar a dívida não pode apagar (nem bloquear) um lançamento do Ledger, que
é append-only e é registro contábil da instituição.

Exclusivamente ADITIVA — nenhum lançamento existente é alterado.

Revision ID: 0128_repasse_withdrawal_debt_link
Revises: 0127_debt_accrual_rates_and_events
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0128_repasse_withdrawal_debt_link"
down_revision = "0127_debt_accrual_rates_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "advance_repasse_ledger",
        sa.Column("debt_item_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_advance_repasse_ledger_debt_item",
        "advance_repasse_ledger",
        "company_financial_items",
        ["debt_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_advance_repasse_ledger_debt_item_id", "advance_repasse_ledger", ["debt_item_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_advance_repasse_ledger_debt_item_id", table_name="advance_repasse_ledger")
    op.drop_constraint(
        "fk_advance_repasse_ledger_debt_item", "advance_repasse_ledger", type_="foreignkey"
    )
    op.drop_column("advance_repasse_ledger", "debt_item_id")
