"""antecipações: documentos anexados à operação (borderô/termo da instituição).

Tabela nova `receivable_advance_batch_attachments` (N arquivos por operação). O arquivo fica em
disco, sob a raiz única de storage (`ADVANCE_BATCH_ATTACHMENT_DIR`, derivado de STORAGE_ROOT ou
da pasta das NFs); o banco guarda só o caminho relativo.

Exclusivamente ADITIVA: nenhuma tabela existente muda.

Revision ID: 0160_advance_batch_attachments
Revises: 0159_fixed_cost_employee_own_value
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0160_advance_batch_attachments"
down_revision = "0159_fixed_cost_employee_own_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receivable_advance_batch_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("receivable_advance_batches.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("receivable_advance_batch_attachments")
