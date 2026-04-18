"""receivable invoices: workflow, finance, cliente, PDF, substituição, log

Revision ID: 0023_receivable_inv
Revises: 0022_projects_view_granular
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0023_receivable_inv"
down_revision = "0022_projects_view_granular"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_invoices",
        sa.Column("status_operacional", sa.String(length=32), nullable=False, server_default="EMITIDA"),
    )
    op.add_column("receivable_invoices", sa.Column("valor_liquido", sa.Numeric(14, 2), nullable=True))
    op.add_column("receivable_invoices", sa.Column("data_quitacao", sa.Date(), nullable=True))
    op.add_column(
        "receivable_invoices",
        sa.Column("cliente_nome_fantasia", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "receivable_invoices",
        sa.Column("cliente_razao_social", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "receivable_invoices",
        sa.Column("numero_documento", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "receivable_invoices",
        sa.Column("nf_substituida_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "receivable_invoices",
        sa.Column("pdf_storage_path", sa.String(length=512), nullable=True),
    )
    op.add_column("receivable_invoices", sa.Column("observacoes_log", sa.Text(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE receivable_invoices
            SET valor_liquido = valor_bruto
            WHERE valor_liquido IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE receivable_invoices
            SET status_operacional = CASE WHEN antecipada THEN 'ANTECIPADA' ELSE 'EMITIDA' END
            """
        )
    )

    op.alter_column("receivable_invoices", "valor_liquido", nullable=False)

    op.create_foreign_key(
        "fk_receivable_invoices_nf_substituida",
        "receivable_invoices",
        "receivable_invoices",
        ["nf_substituida_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_receivable_invoices_status_operacional",
        "receivable_invoices",
        ["status_operacional"],
        unique=False,
    )
    op.create_index(
        "ix_receivable_invoices_cliente_nome_fantasia",
        "receivable_invoices",
        ["cliente_nome_fantasia"],
        unique=False,
    )

    op.execute(sa.text("ALTER TABLE receivable_invoices ALTER COLUMN status_operacional DROP DEFAULT"))


def downgrade() -> None:
    op.drop_index("ix_receivable_invoices_cliente_nome_fantasia", table_name="receivable_invoices")
    op.drop_index("ix_receivable_invoices_status_operacional", table_name="receivable_invoices")
    op.drop_constraint("fk_receivable_invoices_nf_substituida", "receivable_invoices", type_="foreignkey")
    op.drop_column("receivable_invoices", "observacoes_log")
    op.drop_column("receivable_invoices", "pdf_storage_path")
    op.drop_column("receivable_invoices", "nf_substituida_id")
    op.drop_column("receivable_invoices", "numero_documento")
    op.drop_column("receivable_invoices", "cliente_razao_social")
    op.drop_column("receivable_invoices", "cliente_nome_fantasia")
    op.drop_column("receivable_invoices", "data_quitacao")
    op.drop_column("receivable_invoices", "valor_liquido")
    op.drop_column("receivable_invoices", "status_operacional")
