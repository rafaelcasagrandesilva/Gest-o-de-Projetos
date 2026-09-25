"""Jurídico — multa por atraso da rescisão (art. 477 da CLT) no cadastro do desligado.

Até aqui a multa era anotada nas Observações. Vira um valor próprio da rescisão, ao lado de
`severance_amount` e `fgts_balance` (mesmo tratamento de Dados sensíveis).

Aditiva: coluna nula, nenhum dado existente é alterado.

Revision ID: 0151_legal_person_art477_fine
Revises: 0150_extension_requests_cost
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0151_legal_person_art477_fine"
down_revision = "0150_extension_requests_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "legal_persons",
        sa.Column("art477_fine", sa.Numeric(precision=14, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("legal_persons", "art477_fine")
