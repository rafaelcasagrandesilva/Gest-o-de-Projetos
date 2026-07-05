"""Projetos: documentos (tabela + enum de categoria) e permissões.

Cria a tabela normalizada `project_documents` (N documentos por projeto), o enum
`project_document_category` e insere no catálogo as permissões dedicadas
(projects.documents.view/upload/delete). Puramente documental — não altera nenhuma
regra financeira, dashboard ou indicador.

Revision ID: 0082_project_documents
Revises: 0081_project_contract_start_date
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0082_project_documents"
down_revision = "0081_project_contract_start_date"
branch_labels = None
depends_on = None

_CATEGORIES = ("CONTRATO", "ADITIVO", "CRONOGRAMA", "ART", "MEMORIAL", "LICENCA", "OUTRO")
_PERMISSIONS = ("projects.documents.view", "projects.documents.upload", "projects.documents.delete")


def upgrade() -> None:
    category_enum = postgresql.ENUM(*_CATEGORIES, name="project_document_category")
    category_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "project_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "category",
            postgresql.ENUM(*_CATEGORIES, name="project_document_category", create_type=False),
            nullable=False,
            server_default="OUTRO",
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_documents_project_id", "project_documents", ["project_id"])
    op.create_index("ix_project_documents_category", "project_documents", ["category"])
    op.create_index("ix_project_documents_is_active", "project_documents", ["is_active"])
    op.create_foreign_key(
        "fk_project_document_project",
        "project_documents",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Catálogo de permissões (perfis recebem via presets em código; concessões explícitas intactas).
    now = datetime.now(timezone.utc)
    conn = op.get_bind()
    for name in _PERMISSIONS:
        conn.execute(
            text(
                """
                INSERT INTO permissions (id, created_at, updated_at, name)
                VALUES (gen_random_uuid(), :c, :u, :n)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"c": now, "u": now, "n": name},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name in _PERMISSIONS:
        conn.execute(text("DELETE FROM permissions WHERE name = :n"), {"n": name})
    op.drop_constraint("fk_project_document_project", "project_documents", type_="foreignkey")
    op.drop_index("ix_project_documents_is_active", table_name="project_documents")
    op.drop_index("ix_project_documents_category", table_name="project_documents")
    op.drop_index("ix_project_documents_project_id", table_name="project_documents")
    op.drop_table("project_documents")
    postgresql.ENUM(name="project_document_category").drop(op.get_bind(), checkfirst=True)
