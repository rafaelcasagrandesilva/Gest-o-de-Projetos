"""folha real do mês: Vale Transporte (Vale Transporte CLT).

Adiciona a coluna `vt_amount` em `employee_monthly_payroll_overrides`.
Campo OPCIONAL (NULLABLE): quando preenchido, gera um lançamento independente
"<Colaborador> — Vale Transporte CLT" no Contas a Pagar, seguindo exatamente o
mesmo ciclo de vida do VR ("Benefício CLT"). NÃO é somado ao salário nem ao VR e
NÃO altera nenhum cálculo gerencial do projeto. Exclusivamente ADITIVA — dados
existentes permanecem válidos (coluna nasce NULL = sem lançamento de VT).

Revision ID: 0121_payroll_vt_amount
Revises: 0120_legal_events_timeline_assignments
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0121_payroll_vt_amount"
down_revision = "0120_legal_events_timeline_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employee_monthly_payroll_overrides",
        sa.Column("vt_amount", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employee_monthly_payroll_overrides", "vt_amount")
