"""receivable invoices (NF / contas a receber) + payments

Revision ID: 0013_receivable_invoices
Revises: 0012_company_financial_items
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0013_receivable_invoices"
down_revision = "0012_company_financial_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receivable_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("numero_nf", sa.String(length=64), nullable=False),
        sa.Column("data_emissao", sa.Date(), nullable=False),
        sa.Column("valor_bruto", sa.Numeric(14, 2), nullable=False),
        sa.Column("vencimento", sa.Date(), nullable=False),
        sa.Column("data_prevista_pagamento", sa.Date(), nullable=True),
        sa.Column("numero_pedido", sa.String(length=128), nullable=True),
        sa.Column("numero_conformidade", sa.String(length=128), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("antecipada", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("instituicao", sa.String(length=255), nullable=True),
        sa.Column("taxa_juros_mensal", sa.Numeric(10, 6), nullable=True),
    )
    op.create_index("ix_receivable_invoices_project_id", "receivable_invoices", ["project_id"], unique=False)
    op.create_index("ix_receivable_invoices_data_emissao", "receivable_invoices", ["data_emissao"], unique=False)
    op.create_index("ix_receivable_invoices_vencimento", "receivable_invoices", ["vencimento"], unique=False)
    op.execute(sa.text("ALTER TABLE receivable_invoices ALTER COLUMN antecipada DROP DEFAULT"))

    op.create_table(
        "receivable_invoice_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("receivable_invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("data_recebimento", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index(
        "ix_receivable_invoice_payments_invoice_id", "receivable_invoice_payments", ["invoice_id"], unique=False
    )
    op.create_index(
        "ix_receivable_invoice_payments_data_recebimento",
        "receivable_invoice_payments",
        ["data_recebimento"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_receivable_invoice_payments_data_recebimento", table_name="receivable_invoice_payments")
    op.drop_index("ix_receivable_invoice_payments_invoice_id", table_name="receivable_invoice_payments")
    op.drop_table("receivable_invoice_payments")
    op.drop_index("ix_receivable_invoices_vencimento", table_name="receivable_invoices")
    op.drop_index("ix_receivable_invoices_data_emissao", table_name="receivable_invoices")
    op.drop_index("ix_receivable_invoices_project_id", table_name="receivable_invoices")
    op.drop_table("receivable_invoices")
