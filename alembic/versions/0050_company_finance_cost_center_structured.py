"""Company finance: structured cost center (project_id / system codes).

Revision ID: 0050_company_finance_cost_center_structured
Revises: 0049_company_finance_structural_fields
Create Date: 2026-05-19

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = "0050_company_finance_cost_center_structured"
down_revision = "0049_company_finance_structural_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_items",
        sa.Column("cost_center_project_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "company_financial_items",
        sa.Column("cost_center_system", sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        "fk_company_financial_items_cost_center_project",
        "company_financial_items",
        "projects",
        ["cost_center_project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_company_financial_items_cost_center_project_id"),
        "company_financial_items",
        ["cost_center_project_id"],
        unique=False,
    )

    # Administrativo / Financeiro (rótulos legados e variações comuns).
    op.execute(
        """
        UPDATE company_financial_items
           SET cost_center_system = 'ADMINISTRATIVO',
               cost_center_project_id = NULL,
               cost_center = 'Administrativo'
         WHERE cost_center_project_id IS NULL
           AND (
                lower(trim(coalesce(cost_center, ''))) IN ('administrativo', 'admin')
                OR lower(trim(coalesce(cost_center, ''))) = 'administrativo'
           )
        """
    )
    op.execute(
        """
        UPDATE company_financial_items
           SET cost_center_system = 'FINANCEIRO',
               cost_center_project_id = NULL,
               cost_center = 'Financeiro'
         WHERE cost_center_project_id IS NULL
           AND cost_center_system IS NULL
           AND lower(trim(coalesce(cost_center, ''))) IN ('financeiro', 'financas', 'finance')
        """
    )

    # Projetos pelo nome exato (case-insensitive).
    op.execute(
        """
        UPDATE company_financial_items cfi
           SET cost_center_project_id = p.id,
               cost_center_system = NULL,
               cost_center = p.name
          FROM projects p
         WHERE cfi.cost_center_project_id IS NULL
           AND cfi.cost_center_system IS NULL
           AND p.deleted_at IS NULL
           AND lower(trim(coalesce(cfi.cost_center, ''))) = lower(trim(p.name))
           AND trim(coalesce(cfi.cost_center, '')) <> ''
        """
    )

    # Fallback seguro por tipo.
    op.execute(
        """
        UPDATE company_financial_items
           SET cost_center_system = CASE WHEN tipo = 'endividamento' THEN 'FINANCEIRO' ELSE 'ADMINISTRATIVO' END,
               cost_center_project_id = NULL,
               cost_center = CASE WHEN tipo = 'endividamento' THEN 'Financeiro' ELSE 'Administrativo' END
         WHERE cost_center_project_id IS NULL
           AND cost_center_system IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_company_financial_items_cost_center_project_id"), table_name="company_financial_items")
    op.drop_constraint(
        "fk_company_financial_items_cost_center_project",
        "company_financial_items",
        type_="foreignkey",
    )
    op.drop_column("company_financial_items", "cost_center_system")
    op.drop_column("company_financial_items", "cost_center_project_id")
