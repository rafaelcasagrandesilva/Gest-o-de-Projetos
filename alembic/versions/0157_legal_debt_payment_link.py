"""jurídico × endividamento: o pago do acordo vem do Endividamento/CAP.

- `company_financial_items.legal_case_id`: a dívida que paga o acordo de um PROCESSO. Opcional e
  independente do `legal_person_id` (que segue identificando o desligado, com ou sem processo).
- `legal_cases.paid_source`: de onde vem o "Valor pago" do processo. NULL = digitado no Jurídico
  (como sempre foi); 'ENDIVIDAMENTO' = calculado pela dívida vinculada, somente leitura.
- `legal_debt_link_dismissals`: sugestões de vínculo descartadas, para não voltarem.

Exclusivamente ADITIVA: nenhuma dívida nasce vinculada, nenhum valor muda com a migration.

Revision ID: 0157_legal_debt_payment_link
Revises: 0156_settings_nf_taxes_only
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0157_legal_debt_payment_link"
down_revision = "0156_settings_nf_taxes_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_items",
        sa.Column(
            "legal_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_company_financial_items_legal_case_id", "company_financial_items", ["legal_case_id"]
    )
    op.add_column("legal_cases", sa.Column("paid_source", sa.String(16), nullable=True))
    op.create_table(
        "legal_debt_link_dismissals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_financial_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_cases.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_persons.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("legal_debt_link_dismissals")
    op.drop_column("legal_cases", "paid_source")
    op.drop_index("ix_company_financial_items_legal_case_id", table_name="company_financial_items")
    op.drop_column("company_financial_items", "legal_case_id")
