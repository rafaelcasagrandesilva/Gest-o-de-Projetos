"""Backfill: Centro de Custo do projeto = nome do projeto onde ainda está NULL.

Contexto: o vocabulário de Centros de Custo (combo do cadastro de colaboradores) passou a
ler SOMENTE `projects.cost_center` (e `employees.cost_center`), sem mais usar o nome do
projeto como fallback. Como quase todos os projetos antigos estão com `cost_center = NULL`,
o combo ficou reduzido aos poucos valores existentes.

Esta migration corrige apenas os DADOS: para todo projeto com `cost_center IS NULL`, grava
`cost_center = name`. NÃO reintroduz nenhum fallback em código — a fonte oficial continua
sendo exclusivamente `projects.cost_center`.

Propriedades:
- ADITIVA: nenhuma coluna/tabela é criada ou alterada; só um UPDATE de dados.
- Idempotente: só toca linhas com `cost_center IS NULL`; rodar de novo não muda nada.
- Não altera projetos que já possuem `cost_center` preenchido.
- Não altera nenhuma outra coluna.
- Downgrade CONSERVADOR (no-op): correção de dados de mão única, sem mudança de schema.
  Reverter não faz nada — assim um downgrade nunca apaga Centros de Custo editados
  manualmente após o deploy (inclusive valores que coincidam com o nome do projeto).

Revision ID: 0088_backfill_project_cost_center
Revises: 0087_purge_pre_launch_company_finance_payables
"""

from __future__ import annotations

from alembic import op

revision = "0088_backfill_project_cost_center"
down_revision = "0087_purge_pre_launch_company_finance_payables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Só onde está NULL (idempotente); usa o nome como valor inicial do Centro de Custo.
    op.execute(
        """
        UPDATE projects
           SET cost_center = name
         WHERE cost_center IS NULL
           AND name IS NOT NULL
           AND btrim(name) <> '';
        """
    )


def downgrade() -> None:
    # No-op intencional: o backfill é uma correção de dados de mão única e não altera o
    # schema. Reverter para NULL poderia apagar Centros de Custo ajustados manualmente
    # após o deploy — inclusive valores que por acaso coincidam com o nome do projeto.
    # Como downgrades em produção são raríssimos, preferimos preservar os dados.
    pass
