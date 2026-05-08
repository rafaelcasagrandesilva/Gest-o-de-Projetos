"""invoice anticipations (1:N)

Revision ID: 0034_invoice_anticipations
Revises: 0033_company_finance_debt_renegotiation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_invoice_anticipations"
down_revision = "0033_company_finance_debt_renegotiation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add new payable snapshot type for anticipations
    op.execute("ALTER TYPE payable_snapshot_type ADD VALUE IF NOT EXISTS 'ANTECIPACAO'")

    # 2) Create receivable_invoice_anticipations table (FK -> receivable_invoices)
    op.create_table(
        "receivable_invoice_anticipations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("receivable_invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("institution", sa.String(length=255), nullable=False),
        sa.Column("amount_received", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount_to_repay", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
    )
    op.create_index(
        "ix_receivable_invoice_anticipations_invoice_id",
        "receivable_invoice_anticipations",
        ["invoice_id"],
    )
    op.create_index(
        "ix_receivable_invoice_anticipations_due_date",
        "receivable_invoice_anticipations",
        ["due_date"],
    )

    # 3) Migrate legacy single anticipation fields (if any) into 1 row
    op.execute(
        """
        INSERT INTO receivable_invoice_anticipations (
            id, created_at, updated_at, invoice_id, institution, amount_received, amount_to_repay, due_date
        )
        SELECT
            gen_random_uuid(),
            now(),
            now(),
            i.id,
            COALESCE(NULLIF(i.institution, ''), 'Instituição'),
            i.advance_amount_received,
            i.advance_amount_due,
            i.advance_due_date
        FROM receivable_invoices i
        WHERE
            i.is_anticipated = TRUE
            AND i.advance_amount_received IS NOT NULL AND i.advance_amount_received > 0
            AND i.advance_amount_due IS NOT NULL AND i.advance_amount_due > 0
            AND i.advance_due_date IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM receivable_invoice_anticipations a WHERE a.invoice_id = i.id
            );
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_receivable_invoice_anticipations_due_date",
        table_name="receivable_invoice_anticipations",
    )
    op.drop_index(
        "ix_receivable_invoice_anticipations_invoice_id",
        table_name="receivable_invoice_anticipations",
    )
    op.drop_table("receivable_invoice_anticipations")
    raise NotImplementedError("Downgrade não suportado: alteração de enum payable_snapshot_type.")

