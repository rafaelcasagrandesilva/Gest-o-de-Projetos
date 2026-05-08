"""Finance: payable snapshots (consolidated monthly).

Revision ID: 0028_payable_snapshots
Revises: 0027_chart_accounts_payables, 0026_fix_alembic_version_column
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision = "0028_payable_snapshots"
down_revision = ("0027_chart_accounts_payables", "0026_fix_alembic_version_column")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Usar postgresql.ENUM (não sa.Enum): create_type=False é respeitado no PG e evita que
    # op.create_table dispare CREATE TYPE de novo após .create(checkfirst=True).
    payable_snapshot_type = ENUM(
        "COLLABORATOR",
        "VEHICLE",
        "FIXED_COST",
        "MANUAL",
        name="payable_snapshot_type",
        create_type=False,
    )
    payable_snapshot_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "payable_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("type", payable_snapshot_type, nullable=False),
        sa.Column("ref_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cost_center", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("amount_original", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("amount_final", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("paid", sa.Boolean(), nullable=False),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "month",
            "type",
            "ref_id",
            "project_id",
            "name",
            "category",
            "cost_center",
            name="uq_payable_snapshot_identity",
        ),
    )
    op.create_index(op.f("ix_payable_snapshots_month"), "payable_snapshots", ["month"], unique=False)
    op.create_index(op.f("ix_payable_snapshots_type"), "payable_snapshots", ["type"], unique=False)
    op.create_index(op.f("ix_payable_snapshots_ref_id"), "payable_snapshots", ["ref_id"], unique=False)
    op.create_index(op.f("ix_payable_snapshots_project_id"), "payable_snapshots", ["project_id"], unique=False)
    op.create_index(op.f("ix_payable_snapshots_cost_center"), "payable_snapshots", ["cost_center"], unique=False)
    op.create_index(op.f("ix_payable_snapshots_category"), "payable_snapshots", ["category"], unique=False)
    op.create_index(op.f("ix_payable_snapshots_due_date"), "payable_snapshots", ["due_date"], unique=False)
    op.create_index(op.f("ix_payable_snapshots_payment_date"), "payable_snapshots", ["payment_date"], unique=False)
    op.create_index(op.f("ix_payable_snapshots_paid"), "payable_snapshots", ["paid"], unique=False)

    op.create_table(
        "payable_snapshot_generations",
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("month"),
    )
    op.create_index(
        op.f("ix_payable_snapshot_generations_month"),
        "payable_snapshot_generations",
        ["month"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_payable_snapshot_generations_month"), table_name="payable_snapshot_generations")
    op.drop_table("payable_snapshot_generations")

    op.drop_index(op.f("ix_payable_snapshots_paid"), table_name="payable_snapshots")
    op.drop_index(op.f("ix_payable_snapshots_payment_date"), table_name="payable_snapshots")
    op.drop_index(op.f("ix_payable_snapshots_due_date"), table_name="payable_snapshots")
    op.drop_index(op.f("ix_payable_snapshots_category"), table_name="payable_snapshots")
    op.drop_index(op.f("ix_payable_snapshots_cost_center"), table_name="payable_snapshots")
    op.drop_index(op.f("ix_payable_snapshots_project_id"), table_name="payable_snapshots")
    op.drop_index(op.f("ix_payable_snapshots_ref_id"), table_name="payable_snapshots")
    op.drop_index(op.f("ix_payable_snapshots_type"), table_name="payable_snapshots")
    op.drop_index(op.f("ix_payable_snapshots_month"), table_name="payable_snapshots")
    op.drop_table("payable_snapshots")

    payable_snapshot_type = ENUM(
        "COLLABORATOR",
        "VEHICLE",
        "FIXED_COST",
        "MANUAL",
        name="payable_snapshot_type",
        create_type=False,
    )
    payable_snapshot_type.drop(op.get_bind(), checkfirst=True)
