"""comprovantes dos Componentes Variáveis de Pagamento (reembolso, ajuda de custo, …).

Cria `payment_component_attachments`: N arquivos por lançamento variável.

Os gestores lançam reembolso em dois lugares — Custos do Projeto (mão de obra direta) e
Custos Fixos (colaborador da indireta) — mas ambos gravam a MESMA entidade
(`payment_variable_components`). Por isso o anexo se prende ao componente, e não ao
contexto: uma tabela só atende as duas telas.

Só os metadados ficam no banco; o arquivo mora em disco sob a raiz única de storage
(`STORAGE_ROOT`, ver app/utils/storage.py), como os PDFs de NF e os anexos de ativo.

ON DELETE CASCADE: apagar o lançamento apaga os metadados do comprovante. Os arquivos em
disco são removidos pelo service ANTES do delete do componente
(`PaymentComponentAttachmentService.purge_for_component`), para não deixar órfãos no volume.

Exclusivamente ADITIVA — nenhuma tabela existente é tocada.

Revision ID: 0125_payment_component_attachments
Revises: 0124_revenue_use_nf_amount
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0125_payment_component_attachments"
down_revision = "0124_revenue_use_nf_amount"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_component_attachments",
        # id e timestamps são preenchidos pela aplicação (TimestampUUIDMixin), como nas
        # demais tabelas do projeto — sem server_default, sem dependência de pgcrypto.
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_pca_component",
        "payment_component_attachments",
        "payment_variable_components",
        ["component_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Índice do acesso real: "os comprovantes deste lançamento, do mais novo ao mais antigo".
    op.create_index(
        "ix_payment_component_attachments_component_id",
        "payment_component_attachments",
        ["component_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_component_attachments_component_id",
        table_name="payment_component_attachments",
    )
    op.drop_table("payment_component_attachments")
