"""remove o override "Custos adicionais (R$)" da mão de obra do projeto.

Derruba `project_labors.cost_additional_costs`. O campo somava ao CUSTO GERENCIAL do
colaborador no projeto (rateado pelo %) e nunca alcançou o Contas a Pagar. O caso de uso
passou a ser atendido pelos Componentes Variáveis de Pagamento, que entram a valor de
face E geram título no CAP.

DESTRUTIVA por decisão explícita: os valores existentes (6 linhas, R$ 2.200,00 de um
único colaborador entre 2026-04 e 2026-08) são descartados; o custo gerencial dessas
linhas cai nesse valor. Nenhum título de Contas a Pagar muda, porque o campo nunca
participou da obrigação financeira. O `downgrade` recria a coluna vazia (NULL) — a
estrutura volta, os valores não.

O campo homônimo do CADASTRO RH (`employees.additional_costs`) NÃO é afetado.

Revision ID: 0122_drop_project_labor_additional_costs
Revises: 0121_payroll_vt_amount
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0122_drop_project_labor_additional_costs"
down_revision = "0121_payroll_vt_amount"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("project_labors", "cost_additional_costs")


def downgrade() -> None:
    op.add_column(
        "project_labors",
        sa.Column("cost_additional_costs", sa.Numeric(14, 2), nullable=True),
    )
