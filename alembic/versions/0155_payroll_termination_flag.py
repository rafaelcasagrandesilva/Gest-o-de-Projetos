"""folha real do mês: marcação de rescisão contratual.

Adiciona `is_termination` e `termination_amount` em `employee_monthly_payroll_overrides`.
Marcada, a competência NÃO gera "Salário CLT" no Contas a Pagar (nem pelo holerite nem pelo
salário do cadastro) e o valor da rescisão, se preenchido, gera o lançamento independente
"<Colaborador> — Rescisão CLT". VR/VT/Férias preenchidos seguem gerando os seus lançamentos.
Exclusivamente ADITIVA — nasce false/NULL em todas as linhas.

Revision ID: 0155_payroll_termination_flag
Revises: 0154_legal_fix_inflated_case_values
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0155_payroll_termination_flag"
down_revision = "0154_legal_fix_inflated_case_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employee_monthly_payroll_overrides",
        sa.Column("is_termination", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "employee_monthly_payroll_overrides",
        sa.Column("termination_amount", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employee_monthly_payroll_overrides", "termination_amount")
    op.drop_column("employee_monthly_payroll_overrides", "is_termination")
