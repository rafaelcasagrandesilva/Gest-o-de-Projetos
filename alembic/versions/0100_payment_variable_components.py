"""Componentes Variáveis de Pagamento — cadastro de tipos + coleção de lançamentos.

Cria:
- `payment_component_types`: cadastro data-driven dos tipos (Ajuda de custo, Reembolso,
  Diária, Bonificação, Premiação, Auxílio, Outros pagamentos). Semeado com os 7 padrões;
  o usuário pode criar/editar/inativar em Configurações. Nunca se apaga um tipo em uso.
- `payment_variable_components`: N lançamentos por colaborador × competência, com contexto
  polimórfico (project_labor_id XOR company_financial_item_id). Fonte única para Projetos e
  Custo Fixo; a geração de snapshots produz um lançamento no Contas a Pagar por componente.

Exclusivamente ADITIVA. NÃO altera snapshots históricos nem pagamentos. A coluna legada
`project_labors.cost_pj_additional_cost` é preservada (migração de dados na 0101).

Revision ID: 0100_payment_variable_components
Revises: 0099_payroll_vacation_advance
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0100_payment_variable_components"
down_revision = "0099_payroll_vacation_advance"
branch_labels = None
depends_on = None


_DEFAULT_TYPES = [
    ("Ajuda de custo", "ajuda_custo"),
    ("Reembolso", "reembolso"),
    ("Diária", "diaria"),
    ("Bonificação", "bonificacao"),
    ("Premiação", "premiacao"),
    ("Auxílio", "auxilio"),
    ("Outros pagamentos", "outros_pagamentos"),
]


def upgrade() -> None:
    op.create_table(
        "payment_component_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint("uq_payment_component_types_name", "payment_component_types", ["name"])
    op.create_unique_constraint("uq_payment_component_types_code", "payment_component_types", ["code"])
    op.create_index("ix_payment_component_types_name", "payment_component_types", ["name"])
    op.create_index("ix_payment_component_types_code", "payment_component_types", ["code"])
    op.create_index("ix_payment_component_types_is_active", "payment_component_types", ["is_active"])

    op.create_table(
        "payment_variable_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("project_labor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_financial_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(project_labor_id IS NOT NULL)::int + (company_financial_item_id IS NOT NULL)::int = 1",
            name="ck_payment_variable_component_single_context",
        ),
    )
    op.create_foreign_key(
        "fk_pvc_type", "payment_variable_components", "payment_component_types",
        ["type_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_pvc_employee", "payment_variable_components", "employees",
        ["employee_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_pvc_project_labor", "payment_variable_components", "project_labors",
        ["project_labor_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_pvc_company_item", "payment_variable_components", "company_financial_items",
        ["company_financial_item_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_pvc_type_id", "payment_variable_components", ["type_id"])
    op.create_index("ix_pvc_employee_id", "payment_variable_components", ["employee_id"])
    op.create_index("ix_pvc_competencia", "payment_variable_components", ["competencia"])
    op.create_index("ix_pvc_project_labor_id", "payment_variable_components", ["project_labor_id"])
    op.create_index("ix_pvc_company_item_id", "payment_variable_components", ["company_financial_item_id"])
    op.create_unique_constraint(
        "uq_payment_variable_component_identity",
        "payment_variable_components",
        ["type_id", "project_labor_id", "company_financial_item_id", "competencia", "amount", "note"],
    )

    # Seed dos 7 tipos padrão (idempotente por code).
    now = datetime.now(timezone.utc)
    tbl = sa.table(
        "payment_component_types",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("display_order", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        tbl,
        [
            {
                "id": uuid4(), "name": name, "code": code, "description": None,
                "is_active": True, "display_order": idx, "created_at": now, "updated_at": now,
            }
            for idx, (name, code) in enumerate(_DEFAULT_TYPES, start=1)
        ],
    )


def downgrade() -> None:
    op.drop_table("payment_variable_components")
    op.drop_index("ix_payment_component_types_is_active", table_name="payment_component_types")
    op.drop_index("ix_payment_component_types_code", table_name="payment_component_types")
    op.drop_index("ix_payment_component_types_name", table_name="payment_component_types")
    op.drop_table("payment_component_types")
