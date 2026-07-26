"""folha real do mês: adiantamento de férias (Férias CLT).

Adiciona a coluna `vacation_advance_amount` em `employee_monthly_payroll_overrides`.
Campo OPCIONAL (NULLABLE): quando preenchido, gera um lançamento independente
"<Colaborador> — Férias CLT" no Contas a Pagar, seguindo exatamente o mesmo ciclo
de vida de Salário CLT e Benefício CLT. NÃO é somado ao salário e NÃO altera nenhum
cálculo gerencial do projeto. Exclusivamente ADITIVA — dados existentes permanecem
válidos (coluna nasce NULL = sem lançamento de férias).

Revision ID: 0099_payroll_vacation_advance
Revises: 0098_financial_dashboard_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0099_payroll_vacation_advance"
down_revision = "0098_financial_dashboard_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employee_monthly_payroll_overrides",
        sa.Column("vacation_advance_amount", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employee_monthly_payroll_overrides", "vacation_advance_amount")
