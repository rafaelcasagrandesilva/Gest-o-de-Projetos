"""Jurídico — documentos anexados ao cadastro do desligado.

Rescisão, multa art. 477, FGTS, contrato de trabalho, controle de ponto, comprovantes de
pagamento e outros. O arquivo mora em disco na raiz persistente (`LEGAL_DOCUMENT_DIR`, derivado
de `STORAGE_ROOT`); a tabela guarda só o caminho. Baixa lógica (`is_active`), nunca DELETE.

Aditiva: tabela nova, nada existente é alterado.

Revision ID: 0152_legal_person_documents
Revises: 0151_legal_person_art477_fine
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0152_legal_person_documents"
down_revision = "0151_legal_person_art477_fine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_person_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by_email", sa.String(length=255), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["legal_persons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_legal_person_documents_person_id", "legal_person_documents", ["person_id"])
    op.create_index("ix_legal_person_documents_category", "legal_person_documents", ["category"])
    op.create_index("ix_legal_person_documents_is_active", "legal_person_documents", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_legal_person_documents_is_active", table_name="legal_person_documents")
    op.drop_index("ix_legal_person_documents_category", table_name="legal_person_documents")
    op.drop_index("ix_legal_person_documents_person_id", table_name="legal_person_documents")
    op.drop_table("legal_person_documents")
