"""Contas a pagar: coluna `origin` para rastreabilidade da origem dos lançamentos.

Adiciona `payable_snapshots.origin` (texto curto: PROJECT, FIXED_COST, DEBT, MANUAL,
PAYROLL, ANTECIPACAO, …). Junto com o `ref_id` já existente (ID da origem), permite
rastrear de onde surgiu cada lançamento e serve de base para as automações futuras.

Preservação de dados (100%): apenas `add_column` (nullable). Nenhuma linha existente é
alterada — os registros legados ficam com origin NULL e a leitura infere a origem pelo
`type` quando necessário.

Revision ID: 0084_payable_snapshot_origin
Revises: 0083_master_entity_lifecycle
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0084_payable_snapshot_origin"
down_revision = "0083_master_entity_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payable_snapshots", sa.Column("origin", sa.String(length=32), nullable=True))
    op.create_index("ix_payable_snapshots_origin", "payable_snapshots", ["origin"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payable_snapshots_origin", table_name="payable_snapshots")
    op.drop_column("payable_snapshots", "origin")
