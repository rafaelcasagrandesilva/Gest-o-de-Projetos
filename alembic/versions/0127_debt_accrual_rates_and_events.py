"""Endividamento com motor de saldo: vigências de taxa e eventos de saldo.

Fase 2 de docs/ETAPA0_ENDIVIDAMENTO_MOTOR_DE_SALDO.md. Cria as duas tabelas que faltam para a
dívida deixar de ser um valor parado e virar um saldo que evolui:

- `company_financial_rates` — vigências de taxa. A taxa de um mês é a da MAIOR `valid_from`
  menor ou igual a ele. Mudar a taxa é acrescentar vigência, nunca editar a anterior: o
  histórico do que valia em cada mês fica preservado. Uma vigência com taxa 0 CONGELA a dívida
  a partir daquele mês — é assim que se representa um acordo fechado.
- `company_financial_events` — o que mexe no saldo sem ser pagamento: APORTE (dívida nova),
  ABATIMENTO (perdão/desconto negociado) e ENCARGO_MANUAL (multa, honorário).

E `system_settings.debt_default_monthly_rate` (0,5% a.m. = 6% ao ano), usada SÓ na criação de
uma dívida nova.

**Funcionalmente neutra.** Nenhuma dívida existente ganha vigência de taxa nesta migration, e
sem vigência a taxa é 0 — ou seja, toda dívida cadastrada continua exatamente congelada como
está hoje. Ligar a correção é ato explícito, dívida por dívida (decisão D2 da Etapa 0).

Não há discriminador de modo: a dívida "corre juros" quando tem vigência com taxa > 0, e está
"congelada" quando não tem — os dois estados são o mesmo cálculo, e uma coluna de modo seria
uma segunda fonte de verdade para algo que as vigências já respondem.

Exclusivamente ADITIVA — nenhuma tabela existente é alterada.

Revision ID: 0127_debt_accrual_rates_and_events
Revises: 0126_advance_sgc_renumber_chronological
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0127_debt_accrual_rates_and_events"
down_revision = "0126_advance_sgc_renumber_chronological"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_financial_rates",
        # id e timestamps vêm da aplicação (TimestampUUIDMixin), como nas demais tabelas.
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Sempre primeiro-de-mês (competência). Garantido pelo service.
        sa.Column("valid_from", sa.Date(), nullable=False),
        # 6 casas: 0,5% a.m. = 0.005000; 3% a.m. = 0.030000.
        sa.Column("monthly_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["company_financial_items.id"], ondelete="CASCADE"),
        # Duas taxas na mesma competência tornariam ambíguo qual vale.
        sa.UniqueConstraint("item_id", "valid_from", name="uq_company_financial_rates_item_month"),
    )
    op.create_index(
        "ix_company_financial_rates_item_id", "company_financial_rates", ["item_id"]
    )

    op.create_table(
        "company_financial_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        # APORTE | ABATIMENTO | ENCARGO_MANUAL — validado no service (app/services/debt_accrual.py),
        # sem enum de banco para não exigir migration a cada tipo novo.
        sa.Column("kind", sa.String(24), nullable=False),
        # Sempre positivo: o sinal vem do tipo, não do valor.
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["company_financial_items.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_company_financial_events_item_id", "company_financial_events", ["item_id"]
    )

    # Padrão do SGC para dívidas NOVAS: 0,5% a.m. (6% ao ano). Não retroage a nada.
    op.add_column(
        "system_settings",
        sa.Column(
            "debt_default_monthly_rate",
            sa.Numeric(9, 6),
            nullable=False,
            server_default="0.005000",
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "debt_default_monthly_rate")
    op.drop_index("ix_company_financial_events_item_id", table_name="company_financial_events")
    op.drop_table("company_financial_events")
    op.drop_index("ix_company_financial_rates_item_id", table_name="company_financial_rates")
    op.drop_table("company_financial_rates")
