"""Cancelamento de Alocação (engano, sem efeito financeiro). Exclusivamente ADITIVA.

Acrescenta o terceiro desfecho do vínculo, distinguindo o que antes era ambíguo:

    ATIVA      vínculo vigente
    ENCERRADA  existiu e terminou normalmente — deixou rastro financeiro
    CANCELADA  criado por ENGANO e sem nenhum efeito — o "excluir" seguro

Cria o valor `CANCELADA` no enum e as colunas `cancelled_at` / `cancelled_by_id`. O MOTIVO do
cancelamento vai para a auditoria (`audit_logs.context`), junto com o diff — mesma filosofia
append-only do resto do sistema.

Nenhuma linha existente muda: ninguém nasce CANCELADA e nenhum cálculo lê esses campos. Os filtros
que já exigiam `status = 'ATIVA'` (projeção, teto de rateio, índice único de alocação ativa)
excluem CANCELADA automaticamente, sem precisar de alteração.

Nota: `ALTER TYPE ... ADD VALUE` dentro de transação é suportado desde o PostgreSQL 12 (aqui: 18);
o valor novo não é USADO nesta mesma migration, que é a única restrição que permanece.

Revision ID: 0115_assignment_cancelled
Revises: 0114_assignment_single_active
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0115_assignment_cancelled"
down_revision = "0114_assignment_single_active"
branch_labels = None
depends_on = None


def _has_column(insp, table: str, column: str) -> bool:
    return insp.has_table(table) and column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    op.execute("ALTER TYPE employee_assignment_status ADD VALUE IF NOT EXISTS 'CANCELADA'")

    if not _has_column(insp, "employee_assignments", "cancelled_at"):
        op.add_column(
            "employee_assignments",
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column(insp, "employee_assignments", "cancelled_by_id"):
        op.add_column("employee_assignments", sa.Column("cancelled_by_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_employee_assignments_cancelled_by",
            "employee_assignments",
            "users",
            ["cancelled_by_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Remove as colunas. O VALOR do enum permanece: o PostgreSQL não suporta DROP VALUE, e
    removê-lo exigiria recriar o tipo e reescrever a coluna — risco desproporcional para um
    valor que, sem as colunas, deixa de ser usado."""
    op.drop_constraint(
        "fk_employee_assignments_cancelled_by", "employee_assignments", type_="foreignkey"
    )
    op.drop_column("employee_assignments", "cancelled_by_id")
    op.drop_column("employee_assignments", "cancelled_at")
