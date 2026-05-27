"""Borderô / lote de antecipação de NFs.

Revision ID: 0062_receivable_advance_batches
Revises: 0061_payable_snapshot_competence_audit_note
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM

revision = "0062_receivable_advance_batches"
down_revision = "0061_payable_snapshot_competence_audit_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # create_type=False evita CREATE TYPE duplicado ao criar a tabela (após .create(checkfirst=True)).
    batch_status = ENUM(
        "OPEN",
        "SETTLED",
        "CANCELLED",
        name="receivable_advance_batch_status",
        create_type=False,
    )
    batch_status.create(bind, checkfirst=True)

    if not insp.has_table("receivable_advance_batches"):
        op.create_table(
            "receivable_advance_batches",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("batch_number", sa.String(length=32), nullable=False),
            sa.Column("institution", sa.String(length=255), nullable=False),
            sa.Column("gross_amount", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("received_amount", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("discount_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
            sa.Column("fee_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
            sa.Column("receive_date", sa.Date(), nullable=False),
            sa.Column("repayment_date", sa.Date(), nullable=False),
            sa.Column("observation", sa.Text(), nullable=True),
            sa.Column(
                "status",
                batch_status,
                nullable=False,
                server_default="OPEN",
            ),
            sa.Column("created_by_id", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("batch_number"),
        )
        op.create_index("ix_receivable_advance_batches_batch_number", "receivable_advance_batches", ["batch_number"])
        op.create_index("ix_receivable_advance_batches_receive_date", "receivable_advance_batches", ["receive_date"])
        op.create_index("ix_receivable_advance_batches_status", "receivable_advance_batches", ["status"])

    if not insp.has_table("receivable_advance_batch_items"):
        op.create_table(
            "receivable_advance_batch_items",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("batch_id", sa.Uuid(), nullable=False),
            sa.Column("invoice_id", sa.Uuid(), nullable=False),
            sa.Column("invoice_amount", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.ForeignKeyConstraint(["batch_id"], ["receivable_advance_batches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["invoice_id"], ["receivable_invoices.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("batch_id", "invoice_id", name="uq_advance_batch_item_invoice"),
        )
        op.create_index("ix_receivable_advance_batch_items_batch_id", "receivable_advance_batch_items", ["batch_id"])
        op.create_index("ix_receivable_advance_batch_items_invoice_id", "receivable_advance_batch_items", ["invoice_id"])

    inv_cols = {c["name"] for c in insp.get_columns("receivable_invoices")}
    if "advance_batch_id" not in inv_cols:
        op.add_column(
            "receivable_invoices",
            sa.Column("advance_batch_id", sa.Uuid(), nullable=True),
        )
        op.create_foreign_key(
            "fk_receivable_invoices_advance_batch_id",
            "receivable_invoices",
            "receivable_advance_batches",
            ["advance_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_receivable_invoices_advance_batch_id", "receivable_invoices", ["advance_batch_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("receivable_invoices"):
        inv_cols = {c["name"] for c in insp.get_columns("receivable_invoices")}
        if "advance_batch_id" in inv_cols:
            op.drop_index("ix_receivable_invoices_advance_batch_id", table_name="receivable_invoices")
            op.drop_constraint("fk_receivable_invoices_advance_batch_id", "receivable_invoices", type_="foreignkey")
            op.drop_column("receivable_invoices", "advance_batch_id")

    if insp.has_table("receivable_advance_batch_items"):
        op.drop_index("ix_receivable_advance_batch_items_invoice_id", table_name="receivable_advance_batch_items")
        op.drop_index("ix_receivable_advance_batch_items_batch_id", table_name="receivable_advance_batch_items")
        op.drop_table("receivable_advance_batch_items")

    if insp.has_table("receivable_advance_batches"):
        op.drop_index("ix_receivable_advance_batches_status", table_name="receivable_advance_batches")
        op.drop_index("ix_receivable_advance_batches_receive_date", table_name="receivable_advance_batches")
        op.drop_index("ix_receivable_advance_batches_batch_number", table_name="receivable_advance_batches")
        op.drop_table("receivable_advance_batches")

    batch_status = ENUM(
        "OPEN",
        "SETTLED",
        "CANCELLED",
        name="receivable_advance_batch_status",
        create_type=False,
    )
    batch_status.drop(bind, checkfirst=True)
