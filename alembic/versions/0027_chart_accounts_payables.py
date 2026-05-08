"""Finance: chart of accounts + payables (avulsos) + seed.

Revision ID: 0027_chart_accounts_payables
Revises: 0025_add_payables_receivables_permissions
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0027_chart_accounts_payables"
down_revision = "0025_add_payables_receivables_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = datetime.now(timezone.utc)

    op.create_table(
        "chart_of_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "type",
            sa.Enum("COST", "EXPENSE", name="chart_account_type"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_chart_of_accounts_code"), "chart_of_accounts", ["code"], unique=False)
    op.create_index(op.f("ix_chart_of_accounts_type"), "chart_of_accounts", ["type"], unique=False)

    op.create_table(
        "payables",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("competence", sa.Date(), nullable=False),
        sa.Column("chart_account_id", sa.Uuid(), nullable=False),
        sa.Column("cost_center", sa.String(length=255), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["chart_account_id"], ["chart_of_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payables_supplier_name"), "payables", ["supplier_name"], unique=False)
    op.create_index(op.f("ix_payables_due_date"), "payables", ["due_date"], unique=False)
    op.create_index(op.f("ix_payables_payment_date"), "payables", ["payment_date"], unique=False)
    op.create_index(op.f("ix_payables_competence"), "payables", ["competence"], unique=False)
    op.create_index(op.f("ix_payables_chart_account_id"), "payables", ["chart_account_id"], unique=False)
    op.create_index(op.f("ix_payables_cost_center"), "payables", ["cost_center"], unique=False)
    op.create_index(op.f("ix_payables_project_id"), "payables", ["project_id"], unique=False)

    # Seed (idempotente): códigos base do plano de contas.
    conn = op.get_bind()
    seeds: list[tuple[str, str, str]] = [
        ("SALARIO_BASE", "Salário base", "COST"),
        ("FOLHA_PJ", "Folha PJ", "COST"),
        ("BENEFICIOS", "Benefícios", "COST"),
        ("COMBUSTIVEL", "Combustível", "COST"),
        ("ALUGUEL_VEICULOS", "Aluguel de veículos", "COST"),
        ("CONSULTORIA", "Consultoria", "EXPENSE"),
        ("ADVOCACIA", "Advocacia", "EXPENSE"),
        ("IMPOSTOS", "Impostos", "EXPENSE"),
        ("SEGUROS", "Seguros", "EXPENSE"),
        ("SOFTWARES", "Softwares", "EXPENSE"),
    ]
    for code, name, typ in seeds:
        exists = conn.execute(text("SELECT 1 FROM chart_of_accounts WHERE code = :c"), {"c": code}).fetchone()
        if exists:
            continue
        conn.execute(
            text(
                """
                INSERT INTO chart_of_accounts (id, created_at, updated_at, code, name, type)
                VALUES (gen_random_uuid(), :c_at, :u_at, :code, :name, :typ)
                """
            ),
            {"c_at": now, "u_at": now, "code": code, "name": name, "typ": typ},
        )


def downgrade() -> None:
    op.drop_table("payables")
    op.drop_index(op.f("ix_chart_of_accounts_type"), table_name="chart_of_accounts")
    op.drop_index(op.f("ix_chart_of_accounts_code"), table_name="chart_of_accounts")
    op.drop_table("chart_of_accounts")
    op.execute("DROP TYPE IF EXISTS chart_account_type")

