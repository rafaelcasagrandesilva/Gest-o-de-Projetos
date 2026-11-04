"""jurídico: centro de custo do SGC em cada projeto do cadastro.

- `legal_projects.cost_center_ref`: código sistêmico (ADMINISTRATIVO/FINANCEIRO/RH/ALMOXARIFADO)
  ou UUID de um projeto do SGC, inclusive encerrado. Pré-preenche o centro de custo da dívida de
  um desligado no Endividamento. Nasce NULL: nenhum vínculo é inventado.
- Semeia o cadastro com os nomes de projeto JÁ em uso por desligados e processos que ainda não
  estão cadastrados, para o vínculo poder ser feito na aba Projetos sem redigitar cada nome. Só
  insere (ON CONFLICT DO NOTHING); nada existente é alterado.

Revision ID: 0158_legal_project_cost_center
Revises: 0157_legal_debt_payment_link
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0158_legal_project_cost_center"
down_revision = "0157_legal_debt_payment_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legal_projects", sa.Column("cost_center_ref", sa.String(64), nullable=True))
    op.execute(
        """
        INSERT INTO legal_projects (id, name, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), nome, true, now(), now()
        FROM (
            SELECT DISTINCT btrim(project) AS nome FROM legal_persons
            WHERE project IS NOT NULL AND btrim(project) <> ''
            UNION
            SELECT DISTINCT btrim(project) FROM legal_cases
            WHERE project IS NOT NULL AND btrim(project) <> ''
        ) em_uso
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    # Os nomes semeados ficam: são vocabulário válido e podem já ter sido editados.
    op.drop_column("legal_projects", "cost_center_ref")
