"""receivable invoices: classificação Oficial / Não Oficial.

Adiciona a coluna `is_official` (BOOLEAN NOT NULL DEFAULT TRUE) em
`receivable_invoices`. Substitui a convenção manual de escrever "NÃO OFICIAL"
no número da NF por um atributo próprio.

Migration aditiva: registros antigos recebem TRUE (Oficial) por padrão.
Nenhuma tentativa automática de inferir "NÃO OFICIAL" a partir do número — essa
limpeza será feita manualmente depois. Mudança exclusivamente classificatória,
sem impacto em cálculos, antecipações, recebimentos ou snapshots.

Revision ID: 0072_receivable_is_official
Revises: 0071_receivable_competence_month
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0072_receivable_is_official"
down_revision = "0071_receivable_competence_month"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_invoices",
        sa.Column(
            "is_official",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_index(
        "ix_receivable_invoices_is_official",
        "receivable_invoices",
        ["is_official"],
    )


def downgrade() -> None:
    op.drop_index("ix_receivable_invoices_is_official", table_name="receivable_invoices")
    op.drop_column("receivable_invoices", "is_official")
