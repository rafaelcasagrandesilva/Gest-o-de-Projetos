"""Cadastro de Instituições de Antecipação + vínculo na operação.

Cria a tabela `advance_institutions` (Lepta Multissetorial, Banco Daycoval) e
adiciona `institution_id` (FK nullable) em `receivable_advance_batches`. O campo
texto `institution` é mantido por compatibilidade (legado/Dashboard).

O `operation_profile` (LEPTA, DAYCOVAL, …) é a chave que o AdvanceOperationService
usa para resolver o handler de regras de cada instituição.

Revision ID: 0073_advance_institutions
Revises: 0072_receivable_is_official
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0073_advance_institutions"
down_revision = "0072_receivable_is_official"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advance_institutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("institution_type", sa.String(length=64), nullable=False, server_default="OUTROS"),
        sa.Column("operation_profile", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint("uq_advance_institutions_name", "advance_institutions", ["name"])
    op.create_index("ix_advance_institutions_name", "advance_institutions", ["name"])
    op.create_index("ix_advance_institutions_operation_profile", "advance_institutions", ["operation_profile"])
    op.create_index("ix_advance_institutions_is_active", "advance_institutions", ["is_active"])

    # Seed das duas instituições iniciais.
    now = datetime.now(timezone.utc)
    inst = sa.table(
        "advance_institutions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("institution_type", sa.String),
        sa.column("operation_profile", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        inst,
        [
            {
                "id": uuid4(),
                "name": "Lepta Multissetorial",
                "institution_type": "FIDC",
                "operation_profile": "LEPTA",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid4(),
                "name": "Banco Daycoval",
                "institution_type": "BANCO",
                "operation_profile": "DAYCOVAL",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )

    op.add_column(
        "receivable_advance_batches",
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_receivable_advance_batches_institution_id",
        "receivable_advance_batches",
        ["institution_id"],
    )
    op.create_foreign_key(
        "fk_advance_batch_institution",
        "receivable_advance_batches",
        "advance_institutions",
        ["institution_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_advance_batch_institution", "receivable_advance_batches", type_="foreignkey")
    op.drop_index("ix_receivable_advance_batches_institution_id", table_name="receivable_advance_batches")
    op.drop_column("receivable_advance_batches", "institution_id")
    op.drop_index("ix_advance_institutions_is_active", table_name="advance_institutions")
    op.drop_index("ix_advance_institutions_operation_profile", table_name="advance_institutions")
    op.drop_index("ix_advance_institutions_name", table_name="advance_institutions")
    op.drop_constraint("uq_advance_institutions_name", "advance_institutions", type_="unique")
    op.drop_table("advance_institutions")
