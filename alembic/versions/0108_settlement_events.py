"""Antecipações — Evento de Liquidação (agrupador append-only). ADITIVA.

Introduz o conceito de **Evento de Liquidação** acima das movimentações: um pagamento/liquidação
(evento financeiro) que quita 1..N obrigações, agnóstico ao canal de origem. Cria:
- enums nativos `settlement_event_creation_source` (MANUAL/MASS) e `settlement_event_status`
  (ACTIVE/PARTIALLY_REVERSED/FULLY_REVERSED — os 3 já criados p/ evolução futura sem migration);
- tabela `advance_settlement_events` (reusa o enum existente `advance_funding_source`);
- coluna nullable `advance_settlement_movements.event_id` (FK SET NULL) — só agrupamento.

Puramente ADITIVA e reversível: sem backfill, sem tocar dados/movimentações existentes. O Evento
NÃO referencia o Ledger (separação Evento → Movimentações → Ledger preservada).

Revision ID: 0108_settlement_events
Revises: 0107_repasse_withdrawal
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM

revision = "0108_settlement_events"
down_revision = "0107_repasse_withdrawal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    creation_source = ENUM(
        "MANUAL", "MASS", name="settlement_event_creation_source", create_type=False
    )
    status = ENUM(
        "ACTIVE",
        "PARTIALLY_REVERSED",
        "FULLY_REVERSED",
        name="settlement_event_status",
        create_type=False,
    )
    creation_source.create(bind, checkfirst=True)
    status.create(bind, checkfirst=True)
    # Reusa o enum já existente (não recria o tipo).
    funding_source = ENUM(name="advance_funding_source", create_type=False)

    if not insp.has_table("advance_settlement_events"):
        op.create_table(
            "advance_settlement_events",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("creation_source", creation_source, nullable=False),
            sa.Column("status", status, nullable=False),
            sa.Column("institution_id", sa.Uuid(), nullable=False),
            sa.Column("funding_source", funding_source, nullable=True),
            sa.Column("payment_date", sa.Date(), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("invoice_count", sa.Integer(), nullable=False),
            sa.Column("observation", sa.Text(), nullable=True),
            sa.Column("created_by_id", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["institution_id"], ["advance_institutions.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("number", name="uq_advance_settlement_events_number"),
        )
        op.create_index("ix_ase_number", "advance_settlement_events", ["number"], unique=True)
        op.create_index("ix_ase_institution_id", "advance_settlement_events", ["institution_id"])
        op.create_index("ix_ase_payment_date", "advance_settlement_events", ["payment_date"])
        op.create_index("ix_ase_creation_source", "advance_settlement_events", ["creation_source"])
        op.create_index("ix_ase_status", "advance_settlement_events", ["status"])
        op.create_index("ix_ase_created_by_id", "advance_settlement_events", ["created_by_id"])

    cols = {c["name"] for c in insp.get_columns("advance_settlement_movements")}
    if "event_id" not in cols:
        op.add_column(
            "advance_settlement_movements",
            sa.Column("event_id", sa.Uuid(), nullable=True),
        )
        op.create_foreign_key(
            "fk_asm_event_id",
            "advance_settlement_movements",
            "advance_settlement_events",
            ["event_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_asm_event_id", "advance_settlement_movements", ["event_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    cols = {c["name"] for c in insp.get_columns("advance_settlement_movements")}
    if "event_id" in cols:
        op.drop_index("ix_asm_event_id", table_name="advance_settlement_movements")
        op.drop_constraint("fk_asm_event_id", "advance_settlement_movements", type_="foreignkey")
        op.drop_column("advance_settlement_movements", "event_id")

    if insp.has_table("advance_settlement_events"):
        op.drop_table("advance_settlement_events")

    ENUM(name="settlement_event_status", create_type=False).drop(bind, checkfirst=True)
    ENUM(name="settlement_event_creation_source", create_type=False).drop(bind, checkfirst=True)
