"""Jurídico — trilha de auditoria das importações. Exclusivamente ADITIVA (tabela nova).

Uma linha por importação CONFIRMADA: quando, quem, quais arquivos, quantas linhas foram lidas e
o saldo da carga (criados, atualizados, sem alteração, ignorados, duplicados, erros, avisos) mais
o tempo de execução. A pré-visualização não gera registro — ela não altera nada.

Não guarda valores monetários nem conteúdo dos registros: é o QUE aconteceu, não o dado. Assim o
histórico é legível por quem administra o módulo sem depender de Dados sensíveis.

Nenhuma tabela existente é alterada e nenhuma permissão é criada — a leitura usa
`legal_imports.list`, que já existe desde a 0116.

Revision ID: 0117_legal_import_runs
Revises: 0116_legal_import_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0117_legal_import_runs"
down_revision = "0116_legal_import_permissions"
branch_labels = None
depends_on = None

_TABLE = "legal_import_runs"

_COUNTERS = (
    "rows_read",
    "people_new",
    "people_updated",
    "cases_new",
    "cases_updated",
    "unchanged",
    "ignored",
    "duplicates",
    "errors",
    "warnings",
    "duration_ms",
)


def upgrade() -> None:
    if inspect(op.get_bind()).has_table(_TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spreadsheet_name", sa.String(255), nullable=False),
        # NULL = importação só com a planilha (o padrão depois da carga inicial).
        sa.Column("panel_name", sa.String(255), nullable=True),
        *(
            sa.Column(name, sa.Integer(), nullable=False, server_default="0")
            for name in _COUNTERS
        ),
        sa.Column("executed_by_id", sa.Uuid(), nullable=True),
        sa.Column("executed_by_email", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["executed_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    # A tela lista sempre em ordem cronológica decrescente.
    op.create_index(f"ix_{_TABLE}_created_at", _TABLE, ["created_at"])


def downgrade() -> None:
    op.drop_index(f"ix_{_TABLE}_created_at", table_name=_TABLE)
    op.drop_table(_TABLE)
