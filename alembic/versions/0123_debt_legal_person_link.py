"""endividamento de ex-colaborador: vínculo com a pessoa do Jurídico.

Adiciona `legal_person_id` em `company_financial_items`.

Por que uma coluna nova em vez de reaproveitar `employee_id`: `legal_persons` é um cadastro
PRÓPRIO do módulo Jurídico e praticamente disjunto de `employees` — das 159 pessoas desligadas,
apenas 6 têm nome igual a algum colaborador do cadastro operacional. A maioria nunca esteve lá.
Forçar o cadastro operacional a recebê-las poluiria toda tela que lista colaboradores.

Um endividamento trabalhista é justamente com quem já saiu, então o vínculo é com a pessoa do
Jurídico. Em Endividamento o vínculo é SÓ identificação (define o nome do item) — nenhum cálculo
financeiro depende dele, exatamente como já acontece com `employee_id`.

ON DELETE SET NULL: apagar a pessoa no Jurídico não pode apagar um título financeiro; o item
sobrevive com o nome que já tem.

Exclusivamente ADITIVA — nasce NULL em todos os registros existentes.

Revision ID: 0123_debt_legal_person_link
Revises: 0122_drop_project_labor_additional_costs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0123_debt_legal_person_link"
down_revision = "0122_drop_project_labor_additional_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_items",
        sa.Column("legal_person_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_company_financial_items_legal_person_id",
        "company_financial_items",
        ["legal_person_id"],
    )
    op.create_foreign_key(
        "fk_company_financial_items_legal_person_id",
        "company_financial_items",
        "legal_persons",
        ["legal_person_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_company_financial_items_legal_person_id", "company_financial_items", type_="foreignkey"
    )
    op.drop_index("ix_company_financial_items_legal_person_id", table_name="company_financial_items")
    op.drop_column("company_financial_items", "legal_person_id")
