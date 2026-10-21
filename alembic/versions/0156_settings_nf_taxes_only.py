"""configurações: simulação "só impostos da NF".

Adiciona `nf_taxes_only` em `system_settings`. Ligada, os tributos passam a ser só as retenções
da NF (6,15%); os parâmetros do regime tributário não são tocados. Exclusivamente ADITIVA — nasce
false, então nenhum número muda com a migration.

Revision ID: 0156_settings_nf_taxes_only
Revises: 0155_payroll_termination_flag
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0156_settings_nf_taxes_only"
down_revision = "0155_payroll_termination_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("nf_taxes_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "nf_taxes_only")
