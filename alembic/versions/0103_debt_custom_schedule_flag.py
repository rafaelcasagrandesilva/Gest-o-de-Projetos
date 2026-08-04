"""Cronograma Financeiro Personalizado (Endividamento) — Fase 1: flag. ADITIVA.

Introduz o discriminador de modo do endividamento renegociado:

- `company_financial_items.+ uses_custom_schedule BOOLEAN NOT NULL DEFAULT false`
  - false (todos os legados) → Modo 1 "parcelas iguais": comportamento ATUAL, inalterado.
  - true  → Modo 2 "cronograma financeiro personalizado": o conjunto de LANÇAMENTOS
    (company_financial_payments) é a fonte oficial da execução da dívida; cada linha vira um
    título no Contas a Pagar por `entry_id` (infra já existente dos múltiplos lançamentos).

Puramente ADITIVA e reversível: coluna com default seguro, sem backfill, sem tocar dados,
tipos, enums, títulos do CAP ou pagamentos existentes. Nenhum item entra no Modo 2 até que o
flag seja explicitamente ligado (dormant nesta fase).

Escolhemos uma coluna booleana dedicada em vez de estender o enum `renegotiation_type` com um
valor novo, porque `ALTER TYPE ... ADD VALUE` no Postgres não roda em transação e não é
reversível — a coluna é aditiva e desfeita por `DROP COLUMN`.

Revision ID: 0103_debt_custom_schedule_flag
Revises: 0102_payable_snapshot_entry_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0103_debt_custom_schedule_flag"
down_revision = "0102_payable_snapshot_entry_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_financial_items",
        sa.Column(
            "uses_custom_schedule",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("company_financial_items", "uses_custom_schedule")
