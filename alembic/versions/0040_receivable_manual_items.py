"""receivable manual items

Revision ID: 0040_receivable_manual_items
Revises: 0039_user_soft_delete
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0040_receivable_manual_items"
down_revision = "0039_user_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE receivable_manual_status AS ENUM ('ABERTO', 'PARCIAL', 'RECEBIDO'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.create_table(
        "receivable_manual_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False, server_default="finance"),
        sa.Column("descricao", sa.String(length=255), nullable=False),
        sa.Column("cliente", sa.String(length=255), nullable=False),
        sa.Column("numero_referencia", sa.String(length=64), nullable=True),
        sa.Column("data_emissao", sa.Date(), nullable=False),
        sa.Column("data_vencimento", sa.Date(), nullable=False),
        sa.Column("valor_liquido", sa.Numeric(14, 2), nullable=False),
        sa.Column("valor_recebido", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("data_recebimento", sa.Date(), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("ABERTO", "PARCIAL", "RECEBIDO", name="receivable_manual_status", create_type=False),
            nullable=False,
            server_default="ABERTO",
        ),
    )
    op.create_index("ix_receivable_manual_items_workspace_id", "receivable_manual_items", ["workspace_id"])
    op.create_index("ix_receivable_manual_items_cliente", "receivable_manual_items", ["cliente"])
    op.create_index("ix_receivable_manual_items_data_emissao", "receivable_manual_items", ["data_emissao"])
    op.create_index("ix_receivable_manual_items_data_vencimento", "receivable_manual_items", ["data_vencimento"])


def downgrade() -> None:
    op.drop_index("ix_receivable_manual_items_data_vencimento", table_name="receivable_manual_items")
    op.drop_index("ix_receivable_manual_items_data_emissao", table_name="receivable_manual_items")
    op.drop_index("ix_receivable_manual_items_cliente", table_name="receivable_manual_items")
    op.drop_index("ix_receivable_manual_items_workspace_id", table_name="receivable_manual_items")
    op.drop_table("receivable_manual_items")
    op.execute("DROP TYPE IF EXISTS receivable_manual_status")

