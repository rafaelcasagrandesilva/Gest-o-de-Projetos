"""company finance: flag is_monthly_required (custos fixos obrigatórios).

Adiciona a coluna booleana `is_monthly_required` em `company_financial_items`.
Serve apenas para controle operacional (detectar competências sem valor lançado
em itens obrigatórios). Não altera regras financeiras, cálculos ou lançamentos.

Revision ID: 0067_company_finance_monthly_required
Revises: 0066_indicators_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0067_company_finance_monthly_required"
down_revision = "0066_indicators_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_items",
        sa.Column(
            "is_monthly_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("company_financial_items", "is_monthly_required")
