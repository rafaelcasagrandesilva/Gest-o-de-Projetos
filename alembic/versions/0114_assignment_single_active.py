"""Uma Alocação ATIVA por (colaborador, projeto). Estrutural, sem mudança de dados.

`governing()` escolhe QUAL alocação projeta o valor na linha mensal de `project_labors`. Com duas
alocações ativas para o mesmo par, essa escolha seria ambígua e o valor projetado, imprevisível —
exatamente a classe de bug do desempate por cenário corrigido na 0113, só que atingindo dinheiro.

O serviço já valida e devolve mensagem legível; este índice é a rede de segurança no banco, para
que nenhuma escrita fora do serviço (script, importador futuro, correção manual) crie a ambiguidade.

Índice PARCIAL de propósito:
- só `status = 'ATIVA'` → o histórico pode ter N alocações encerradas do mesmo par, que é o
  comportamento desejado (sair de um contrato e voltar depois);
- só `project_id IS NOT NULL` → alocações apenas de Centro de Custo (sem contrato) podem coexistir.

Dados atuais já satisfazem: 81 alocações com projeto para 81 pares distintos.

Revision ID: 0114_assignment_single_active
Revises: 0113_fix_assignment_backfill_scenario
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0114_assignment_single_active"
down_revision = "0113_fix_assignment_backfill_scenario"
branch_labels = None
depends_on = None

_INDEX = "uq_employee_assignment_active_project"


def upgrade() -> None:
    op.create_index(
        _INDEX,
        "employee_assignments",
        ["employee_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ATIVA' AND project_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="employee_assignments")
