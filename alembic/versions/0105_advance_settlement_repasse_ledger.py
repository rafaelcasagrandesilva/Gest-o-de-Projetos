"""Antecipações — Liquidação de NFs + Ledger de Repasse (Fase 1A: infraestrutura). ADITIVA.

Cria a infraestrutura DORMENTE do controle de liquidação da obrigação perante a instituição e do
extrato (Ledger) de Repasse. Nesta fase **nada** do comportamento atual muda: a LEPTA continua
gerando Repasse no Contas a Pagar; as tabelas/enums abaixo nascem vazias e sem integração.

Cria:
- enums nativos `advance_funding_source`, `repasse_ledger_direction`, `repasse_ledger_source`;
- `advance_settlement_movements` — movimentações de liquidação (1:N por obrigação = participação
  NF × operação `receivable_advance_batch_items`); append-only, estorno via `reversed_at`;
- `advance_repasse_ledger` — extrato append-only por instituição (CREDIT/DEBIT).

Puramente ADITIVA e reversível: sem backfill, sem tocar tabelas/dados/enums existentes (NFs, CAP,
operações). O backfill do Ledger e a mudança de comportamento (repasse sai do CAP) são da Fase 1B
(migration futura). Reversível por `drop_table`/`drop_type` (downgrade).

Revision ID: 0105_advance_settlement_repasse_ledger
Revises: 0104_payment_schedule_seq
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM

revision = "0105_advance_settlement_repasse_ledger"
down_revision = "0104_payment_schedule_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # create_type=False evita CREATE TYPE duplicado ao criar a tabela (após .create(checkfirst=True)).
    funding_source = ENUM(
        "SALDO_REPASSE",
        "RECEBIMENTO_CLIENTE",
        "ANTECIPACAO_DAYCOVAL",
        "CAIXA_EMPRESA",
        "OUTRA",
        name="advance_funding_source",
        create_type=False,
    )
    ledger_direction = ENUM("CREDIT", "DEBIT", name="repasse_ledger_direction", create_type=False)
    ledger_source = ENUM(
        "OPERATION", "SETTLEMENT", "ADJUSTMENT", name="repasse_ledger_source", create_type=False
    )
    funding_source.create(bind, checkfirst=True)
    ledger_direction.create(bind, checkfirst=True)
    ledger_source.create(bind, checkfirst=True)

    # --- movimentações de liquidação (criada ANTES do ledger: o ledger a referencia) ---------
    if not insp.has_table("advance_settlement_movements"):
        op.create_table(
            "advance_settlement_movements",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("batch_item_id", sa.Uuid(), nullable=False),
            sa.Column("batch_id", sa.Uuid(), nullable=False),
            sa.Column("invoice_id", sa.Uuid(), nullable=False),
            sa.Column("institution_id", sa.Uuid(), nullable=False),
            sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("funding_source", funding_source, nullable=False),
            sa.Column("settled_at", sa.Date(), nullable=False),
            sa.Column("observation", sa.Text(), nullable=True),
            sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reversal_reason", sa.Text(), nullable=True),
            sa.Column("created_by_id", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(
                ["batch_item_id"], ["receivable_advance_batch_items.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["batch_id"], ["receivable_advance_batches.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["invoice_id"], ["receivable_invoices.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["institution_id"], ["advance_institutions.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_asm_batch_item_id", "advance_settlement_movements", ["batch_item_id"])
        op.create_index("ix_asm_batch_id", "advance_settlement_movements", ["batch_id"])
        op.create_index("ix_asm_invoice_id", "advance_settlement_movements", ["invoice_id"])
        op.create_index("ix_asm_institution_id", "advance_settlement_movements", ["institution_id"])
        op.create_index("ix_asm_funding_source", "advance_settlement_movements", ["funding_source"])
        op.create_index("ix_asm_settled_at", "advance_settlement_movements", ["settled_at"])
        op.create_index("ix_asm_reversed_at", "advance_settlement_movements", ["reversed_at"])
        op.create_index("ix_asm_created_by_id", "advance_settlement_movements", ["created_by_id"])

    # --- extrato (ledger) de repasse ----------------------------------------------------------
    if not insp.has_table("advance_repasse_ledger"):
        op.create_table(
            "advance_repasse_ledger",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("institution_id", sa.Uuid(), nullable=False),
            sa.Column("direction", ledger_direction, nullable=False),
            sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("source_type", ledger_source, nullable=False),
            sa.Column("source_batch_id", sa.Uuid(), nullable=True),
            sa.Column("source_movement_id", sa.Uuid(), nullable=True),
            sa.Column("occurred_at", sa.Date(), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reversal_reason", sa.Text(), nullable=True),
            sa.Column("created_by_id", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["institution_id"], ["advance_institutions.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["source_batch_id"], ["receivable_advance_batches.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["source_movement_id"], ["advance_settlement_movements.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_arl_institution_id", "advance_repasse_ledger", ["institution_id"])
        op.create_index("ix_arl_direction", "advance_repasse_ledger", ["direction"])
        op.create_index("ix_arl_source_type", "advance_repasse_ledger", ["source_type"])
        op.create_index("ix_arl_source_batch_id", "advance_repasse_ledger", ["source_batch_id"])
        op.create_index("ix_arl_source_movement_id", "advance_repasse_ledger", ["source_movement_id"])
        op.create_index("ix_arl_occurred_at", "advance_repasse_ledger", ["occurred_at"])
        op.create_index("ix_arl_reversed_at", "advance_repasse_ledger", ["reversed_at"])
        op.create_index("ix_arl_created_by_id", "advance_repasse_ledger", ["created_by_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("advance_repasse_ledger"):
        op.drop_table("advance_repasse_ledger")
    if insp.has_table("advance_settlement_movements"):
        op.drop_table("advance_settlement_movements")

    ENUM(name="repasse_ledger_source", create_type=False).drop(bind, checkfirst=True)
    ENUM(name="repasse_ledger_direction", create_type=False).drop(bind, checkfirst=True)
    ENUM(name="advance_funding_source", create_type=False).drop(bind, checkfirst=True)
