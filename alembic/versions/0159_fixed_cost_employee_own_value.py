"""custos fixos: colaborador com VALOR PRÓPRIO + natureza do pagamento.

O tipo Colaborador dos Custos Fixos (`COLABORADOR_MATRIZ`) calcula o valor como custo do
colaborador × percentual — não serve para quem recebe um valor próprio que não é salário
(ex.: Retirada de Capital dos sócios). Esta migration:

- acrescenta `COLABORADOR_VALOR` ao enum `company_financial_item_type`: item ligado ao
  colaborador cujo valor vem da referência/grade, como no Manual;
- cria `company_financial_items.payment_component_type_id` (FK → payment_component_types): a
  NATUREZA do pagamento. O título do Contas a Pagar sai "<Colaborador> — <Natureza>";
- semeia o tipo "Retirada de Capital" (code `retirada_capital`), se ainda não existir.

Exclusivamente ADITIVA: nenhum item muda de tipo e nenhum título é tocado aqui. A conversão
dos itens existentes é feita pela tela (Editar estrutura).

ATENÇÃO à numeração: 0157/0158 (Jurídico × Endividamento) estão em outra branch. Quem for
mergeado por último aponta `down_revision` para a cabeça do outro.

Revision ID: 0159_fixed_cost_employee_own_value
Revises: 0158_legal_project_cost_center
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0159_fixed_cost_employee_own_value"
down_revision = "0158_legal_project_cost_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE company_financial_item_type ADD VALUE IF NOT EXISTS 'COLABORADOR_VALOR'")
    op.add_column(
        "company_financial_items",
        sa.Column(
            "payment_component_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payment_component_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_company_financial_items_payment_component_type_id",
        "company_financial_items",
        ["payment_component_type_id"],
    )
    op.execute(
        """
        INSERT INTO payment_component_types
            (id, name, code, description, is_active, display_order, created_at, updated_at)
        SELECT gen_random_uuid(), 'Retirada de Capital', 'retirada_capital',
               'Retirada de capital dos sócios — não é remuneração.', true,
               COALESCE((SELECT MAX(display_order) FROM payment_component_types), 0) + 1,
               now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM payment_component_types
            WHERE code = 'retirada_capital' OR lower(name) = 'retirada de capital'
        )
        """
    )


def downgrade() -> None:
    # O valor do enum fica (Postgres não remove valor de enum); itens que o usam voltam a Manual.
    op.execute(
        "UPDATE company_financial_items SET item_type = 'MANUAL', employee_id = NULL "
        "WHERE item_type = 'COLABORADOR_VALOR'"
    )
    op.drop_index(
        "ix_company_financial_items_payment_component_type_id", table_name="company_financial_items"
    )
    op.drop_column("company_financial_items", "payment_component_type_id")
    op.execute(
        """
        DELETE FROM payment_component_types t
        WHERE t.code = 'retirada_capital'
          AND NOT EXISTS (SELECT 1 FROM payment_variable_components c WHERE c.type_id = t.id)
        """
    )
