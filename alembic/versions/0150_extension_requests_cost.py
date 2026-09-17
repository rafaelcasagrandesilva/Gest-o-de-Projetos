"""Liquidação de NFs: pedido de prorrogação com CUSTO (uma ou várias NFs).

A instituição informa o custo do pedido inteiro (uma NF ou várias para a mesma data), pago no dia
do pedido. `advance_extension_requests` guarda o pedido (nova data, custo, data do pagamento, título
gerado no Contas a Pagar); cada prorrogação de NF aponta para o seu pedido (`request_id`).

Aditiva. Prorrogações antigas (sem pedido) continuam válidas.

Revision ID: 0150_extension_requests_cost
Revises: 0149_obligation_extension_interest
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0150_extension_requests_cost"
down_revision = "0149_obligation_extension_interest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advance_extension_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("institution_name", sa.Text(), nullable=True),
        sa.Column("new_due", sa.Date(), nullable=False),
        sa.Column("cost_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("cost_payment_date", sa.Date(), nullable=False),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("payable_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["institution_id"], ["advance_institutions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payable_snapshot_id"], ["payable_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_advance_extension_requests_institution_id", "advance_extension_requests", ["institution_id"]
    )
    op.add_column(
        "advance_obligation_extensions",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_advance_obligation_extensions_request_id", "advance_obligation_extensions",
        "advance_extension_requests", ["request_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index(
        "ix_advance_obligation_extensions_request_id", "advance_obligation_extensions", ["request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_advance_obligation_extensions_request_id", table_name="advance_obligation_extensions")
    op.drop_constraint(
        "fk_advance_obligation_extensions_request_id", "advance_obligation_extensions", type_="foreignkey"
    )
    op.drop_column("advance_obligation_extensions", "request_id")
    op.drop_index("ix_advance_extension_requests_institution_id", table_name="advance_extension_requests")
    op.drop_table("advance_extension_requests")
