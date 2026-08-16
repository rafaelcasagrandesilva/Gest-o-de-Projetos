"""Corrige o backfill das Alocações: desempate por CENÁRIO. Só toca linhas criadas pela 0112.

Defeito corrigido: a 0112 escolheu a linha de origem com
`DISTINCT ON (employee_id, project_id) ... ORDER BY ... competencia DESC`, ignorando que existem
DOIS cenários por competência (PREVISTO e REALIZADO). Com empate na competência, o Postgres podia
devolver qualquer um dos dois — e devolveu o PREVISTO em pelo menos um caso real (João Carlos /
Treinamentos: alocação ficou 15% do PREVISTO em vez de 10% do REALIZADO).

Isso NUNCA alterou cálculo: a Alocação não escreve em `project_labors`, e a Folha permaneceu
byte a byte idêntica. Mas o registro contratual precisa espelhar fielmente a realidade — o usuário
exigiu que nenhum percentual fosse alterado, e o espelho estava errado em 1 de 6 rateios.

Regra determinística agora: competência mais recente e, no empate, **REALIZADO** (o que de fato
aconteceu) tem prioridade sobre PREVISTO. Reaplica percentual, salário e horas.

Escopo: apenas `employee_assignments` com `is_backfilled = true` E `project_id` preenchido —
alocações cadastradas à mão pelo usuário jamais são tocadas. `project_labors` não é lido para
escrita em lugar nenhum.

Revision ID: 0113_fix_assignment_backfill_scenario
Revises: 0112_employee_assignments
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0113_fix_assignment_backfill_scenario"
down_revision = "0112_employee_assignments"
branch_labels = None
depends_on = None

# Linha de origem canônica de um par (colaborador, projeto): a mais recente; REALIZADO ganha do
# PREVISTO no empate de competência.
_SOURCE = """
    SELECT DISTINCT ON (pl.employee_id, pl.project_id)
           pl.employee_id,
           pl.project_id,
           pl.allocation_percentage        AS pct,
           pl.cost_salary_base             AS salary_base,
           pl.cost_pj_hours_per_month      AS hours
      FROM project_labors pl
     ORDER BY pl.employee_id,
              pl.project_id,
              pl.competencia DESC,
              (pl.scenario::text = 'REALIZADO') DESC
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            f"""
            UPDATE employee_assignments a
               SET allocation_percent = s.pct,
                   -- Tipo é reclassificado junto: se a linha canônica é 100%, é contrato próprio.
                   allocation_type = CASE WHEN s.pct = 100 THEN 'INDEPENDENTE'
                                          ELSE 'RATEIO' END::employee_allocation_type,
                   -- Em RATEIO os campos de remuneração própria não existem (mesma regra do serviço).
                   salary_base = CASE WHEN s.pct = 100 THEN s.salary_base ELSE NULL END,
                   hours_per_month = CASE WHEN s.pct = 100 THEN s.hours ELSE NULL END,
                   updated_at = now()
              FROM ({_SOURCE}) s
             WHERE a.employee_id = s.employee_id
               AND a.project_id  = s.project_id
               AND a.is_backfilled
            """
        )
    )


def downgrade() -> None:
    """Sem volta: o estado anterior era o desempate NÃO determinístico, que não é reproduzível."""
