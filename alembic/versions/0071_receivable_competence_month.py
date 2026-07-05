"""receivable invoices: competência mensal (mês/ano do serviço executado).

Adiciona a coluna `competence_month` (DATE, primeiro-de-mês) em
`receivable_invoices`. Representa o período em que o serviço foi executado,
independente da data de emissão. NULLABLE — registros antigos permanecem NULL,
sem alteração de comportamento. Obrigatoriedade aplica-se apenas a novas NFs
(validada na camada de aplicação).

Revision ID: 0071_receivable_competence_month
Revises: 0070_company_finance_renegotiation_schedule
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0071_receivable_competence_month"
down_revision = "0070_company_finance_renegotiation_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receivable_invoices",
        sa.Column("competence_month", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_receivable_invoices_competence_month",
        "receivable_invoices",
        ["competence_month"],
    )


def downgrade() -> None:
    op.drop_index("ix_receivable_invoices_competence_month", table_name="receivable_invoices")
    op.drop_column("receivable_invoices", "competence_month")
