"""receivable_invoices: modelo financeiro simplificado; remove pagamentos parciais.

Revision ID: 0024_receivable_simplified
Revises: 0023_receivable_inv
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0024_receivable_simplified"
down_revision = "0023_receivable_inv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        text(
            "ALTER TABLE receivable_invoices DROP CONSTRAINT IF EXISTS fk_receivable_invoices_nf_substituida"
        )
    )

    op.add_column(
        "receivable_invoices",
        sa.Column("received_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )
    op.add_column("receivable_invoices", sa.Column("received_date", sa.Date(), nullable=True))
    op.add_column(
        "receivable_invoices",
        sa.Column("due_days", sa.Integer(), nullable=False, server_default="30"),
    )

    conn.execute(
        text(
            """
            UPDATE receivable_invoices ri
            SET received_amount = COALESCE(s.tot, 0), received_date = s.dt
            FROM (
              SELECT invoice_id, SUM(valor) AS tot, MAX(data_recebimento) AS dt
              FROM receivable_invoice_payments
              GROUP BY invoice_id
            ) s
            WHERE ri.id = s.invoice_id
            """
        )
    )

    op.drop_table("receivable_invoice_payments")

    conn.execute(
        text(
            """
            UPDATE receivable_invoices
            SET due_days = CASE
              WHEN (vencimento - data_emissao) <= 45 THEN 30
              WHEN (vencimento - data_emissao) <= 75 THEN 60
              ELSE 90
            END
            """
        )
    )

    op.add_column("receivable_invoices", sa.Column("client_name", sa.String(512), nullable=True))
    conn.execute(
        text(
            """
            UPDATE receivable_invoices
            SET client_name = NULLIF(TRIM(CONCAT(
              COALESCE(cliente_nome_fantasia, ''),
              CASE WHEN cliente_nome_fantasia IS NOT NULL AND cliente_razao_social IS NOT NULL
                   THEN ' / ' ELSE '' END,
              COALESCE(cliente_razao_social, '')
            )), '')
            """
        )
    )

    op.add_column(
        "receivable_invoices",
        sa.Column("invoice_status", sa.String(32), nullable=False, server_default="EMITIDA"),
    )
    conn.execute(
        text(
            """
            UPDATE receivable_invoices
            SET invoice_status = CASE
              WHEN status_operacional = 'CANCELADA' THEN 'CANCELADA'
              WHEN received_amount >= valor_liquido - 0.01 THEN 'FINALIZADA'
              WHEN antecipada OR status_operacional = 'ANTECIPADA' THEN 'ANTECIPADA'
              ELSE 'EMITIDA'
            END
            """
        )
    )

    op.add_column("receivable_invoices", sa.Column("notes", sa.Text(), nullable=True))
    conn.execute(text("UPDATE receivable_invoices SET notes = observacao"))
    op.add_column("receivable_invoices", sa.Column("activity_log", sa.Text(), nullable=True))
    conn.execute(text("UPDATE receivable_invoices SET activity_log = observacoes_log"))

    renames = [
        ("numero_nf", "nf_number"),
        ("data_emissao", "issue_date"),
        ("valor_bruto", "gross_amount"),
        ("valor_liquido", "net_amount"),
        ("vencimento", "due_date"),
        ("antecipada", "is_anticipated"),
        ("instituicao", "institution"),
        ("pdf_storage_path", "pdf_path"),
    ]
    for old, new in renames:
        conn.execute(text(f"ALTER TABLE receivable_invoices RENAME COLUMN {old} TO {new}"))

    drops = [
        "numero_pedido",
        "numero_conformidade",
        "numero_documento",
        "data_prevista_pagamento",
        "data_quitacao",
        "nf_substituida_id",
        "taxa_juros_mensal",
        "cliente_nome_fantasia",
        "cliente_razao_social",
        "observacao",
        "observacoes_log",
        "status_operacional",
    ]
    for col in drops:
        op.drop_column("receivable_invoices", col)

    conn.execute(
        text("UPDATE receivable_invoices SET due_date = issue_date + (due_days * INTERVAL '1 day')")
    )

    op.alter_column("receivable_invoices", "received_amount", server_default=None)
    op.alter_column("receivable_invoices", "due_days", server_default=None)
    op.alter_column("receivable_invoices", "invoice_status", server_default=None)

    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_receivable_invoices_invoice_status "
            "ON receivable_invoices (invoice_status)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_receivable_invoices_client_name "
            "ON receivable_invoices (client_name)"
        )
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade não suportado para esta revisão.")
