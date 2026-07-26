"""Custos Fixos — MÚLTIPLOS LANÇAMENTOS (Fase 1: CAP). ADITIVA.

Adiciona o vínculo preciso 1:1 entre o título do Contas a Pagar e o LANÇAMENTO de origem,
sustentando N lançamentos do mesmo item na mesma competência sem colidir na identidade única.

Mudanças:
- `payable_snapshots.+ entry_id UUID NULL` → FK para `company_financial_payments(id)`
  ON DELETE SET NULL, indexado. `ref_id` continua apontando para o ITEM (metadados/centro/
  exclusão por item); `entry_id` é a chave por LANÇAMENTO (geração/sync/reconciliação — Fase 2).
- Backfill: para cada título corporativo (FIXED_COST/ENDIVIDAMENTO/FINANCIAL, project_id nulo),
  `entry_id` = id do único lançamento (item_id = ref_id, competência = month). Após a 0101 ainda
  há no máximo um lançamento por (item, mês), então o vínculo é inequívoco.
- Substitui `uq_payable_snapshot_identity` para INCLUIR `entry_id`. Assim N títulos do mesmo
  item/mês (que compartilham month/type/ref_id/name/category/cost_center) deixam de colidir.
  Linhas não-corporativas mantêm `entry_id` NULL (NULLs são distintos no unique do Postgres).

Puramente ADITIVA: não altera amount_*, pagamentos, estornos nem linhas MANUAL. Não cria
lançamentos novos. Backward-compatible: títulos sem lançamento correspondente ficam com
`entry_id` NULL e seguem tratados pela lógica por item (Fase 2 resolve o vínculo adiante).

Revision ID: 0102_payable_snapshot_entry_id
Revises: 0101_fixed_cost_multi_entries
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0102_payable_snapshot_entry_id"
down_revision = "0101_fixed_cost_multi_entries"
branch_labels = None
depends_on = None

_UQ = "uq_payable_snapshot_identity"
_UQ_COLS = ["month", "type", "ref_id", "project_id", "name", "category", "cost_center"]


def upgrade() -> None:
    op.add_column(
        "payable_snapshots",
        sa.Column("entry_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_payable_snapshots_entry_id", "payable_snapshots", ["entry_id"]
    )
    op.create_foreign_key(
        "fk_payable_snapshots_entry_id",
        "payable_snapshots",
        "company_financial_payments",
        ["entry_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill: vincula cada título corporativo ao seu lançamento (1:1, inequívoco pós-0101).
    op.execute(
        """
        UPDATE payable_snapshots AS ps
        SET entry_id = cfp.id
        FROM company_financial_payments AS cfp
        WHERE ps.ref_id = cfp.item_id
          AND ps.month = cfp.competencia
          AND ps.project_id IS NULL
          AND ps.type::text IN ('FIXED_COST', 'ENDIVIDAMENTO', 'FINANCIAL')
          AND ps.entry_id IS NULL
        """
    )

    # Identidade única passa a incluir entry_id (permite N títulos por item/mês).
    op.drop_constraint(_UQ, "payable_snapshots", type_="unique")
    op.create_unique_constraint(_UQ, "payable_snapshots", [*_UQ_COLS, "entry_id"])


def downgrade() -> None:
    op.drop_constraint(_UQ, "payable_snapshots", type_="unique")
    op.create_unique_constraint(_UQ, "payable_snapshots", _UQ_COLS)
    op.drop_constraint("fk_payable_snapshots_entry_id", "payable_snapshots", type_="foreignkey")
    op.drop_index("ix_payable_snapshots_entry_id", table_name="payable_snapshots")
    op.drop_column("payable_snapshots", "entry_id")
