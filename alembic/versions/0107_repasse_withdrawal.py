"""Antecipações — Retirada de Repasse no Ledger (append-only). ADITIVA.

Habilita uma terceira movimentação no extrato (Ledger) de Repasse: além das Entradas (operação de
antecipação) e das Saídas por Liquidação de NF, passa a existir a **Retirada de Repasse** — um DÉBITO
que apenas reduz o saldo disponível do Repasse (não é liquidação de NF). O Ledger permanece genérico
e append-only; nada é editado/excluído.

Cria:
- valor `WITHDRAWAL` no enum existente `repasse_ledger_source` (rótulo genérico da origem);
- tipo nativo `repasse_withdrawal_purpose` (`DEBT_REDUCTION`, `OTHER`);
- coluna nullable `advance_repasse_ledger.withdrawal_purpose` (destino ESTRUTURADO da retirada —
  preenchida só em lançamentos WITHDRAWAL; preparada para futura integração com Endividamento, sem
  qualquer acoplamento agora).

Puramente ADITIVA: sem backfill, sem tocar dados/lançamentos existentes. Reversível (o valor de enum
`WITHDRAWAL` permanece no downgrade — Postgres não remove valores de enum —, o que é inócuo).

Revision ID: 0107_repasse_withdrawal
Revises: 0106_repasse_cap_to_ledger_backfill
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM

revision = "0107_repasse_withdrawal"
down_revision = "0106_repasse_cap_to_ledger_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # Novo valor de origem (não é usado nesta própria migration → não exige autocommit_block).
    op.execute("ALTER TYPE repasse_ledger_source ADD VALUE IF NOT EXISTS 'WITHDRAWAL'")

    # Novo tipo nativo para o destino estruturado da retirada.
    withdrawal_purpose = ENUM(
        "DEBT_REDUCTION", "OTHER", name="repasse_withdrawal_purpose", create_type=False
    )
    withdrawal_purpose.create(bind, checkfirst=True)

    cols = {c["name"] for c in insp.get_columns("advance_repasse_ledger")}
    if "withdrawal_purpose" not in cols:
        op.add_column(
            "advance_repasse_ledger",
            sa.Column("withdrawal_purpose", withdrawal_purpose, nullable=True),
        )
        op.create_index(
            "ix_arl_withdrawal_purpose", "advance_repasse_ledger", ["withdrawal_purpose"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    cols = {c["name"] for c in insp.get_columns("advance_repasse_ledger")}
    if "withdrawal_purpose" in cols:
        op.drop_index("ix_arl_withdrawal_purpose", table_name="advance_repasse_ledger")
        op.drop_column("advance_repasse_ledger", "withdrawal_purpose")

    ENUM(name="repasse_withdrawal_purpose", create_type=False).drop(bind, checkfirst=True)
    # O valor de enum 'WITHDRAWAL' em repasse_ledger_source é mantido (Postgres não remove valores
    # de enum sem recriar o tipo) — inócuo.
