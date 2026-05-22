"""Gestão de Ativos: tabelas + permissões RBAC.

Revision ID: 0051_assets_management_module
Revises: 0050_company_finance_cost_center_structured
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0051_assets_management_module"
down_revision = "0050_company_finance_cost_center_structured"
branch_labels = None
depends_on = None

ASSET_STATUS = ("AVAILABLE", "IN_USE", "MAINTENANCE", "EXPIRED", "LOST", "DISCARDED")
ATTACHMENT_TYPES = (
    "TERM",
    "REPORT",
    "CERTIFICATE",
    "INVOICE",
    "MANUAL",
    "PHOTO",
    "MAINTENANCE_ORDER",
    "OTHER",
)


def _ensure_pg_enums():
    """Cria tipos ENUM no Postgres (idempotente) e retorna colunas sem recriar o tipo."""
    for values, name in ((ASSET_STATUS, "asset_status"), (ATTACHMENT_TYPES, "asset_attachment_type")):
        sa.Enum(*values, name=name).create(op.get_bind(), checkfirst=True)
    return (
        PG_ENUM(*ASSET_STATUS, name="asset_status", create_type=False),
        PG_ENUM(*ATTACHMENT_TYPES, name="asset_attachment_type", create_type=False),
    )


def upgrade() -> None:
    asset_status, attachment_type = _ensure_pg_enums()
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("assets"):
        # Migração parcial anterior: tipos já existem, tabelas também — só permissões.
        pass
    else:
        _create_asset_tables(asset_status, attachment_type)

    conn = bind
    now = datetime.now(timezone.utc)
    for code in (
        "workspace.assets.access",
        "assets.view",
        "assets.edit",
    ):
        exists = conn.execute(sa.text("SELECT 1 FROM permissions WHERE name = :n"), {"n": code}).fetchone()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), :c, :u, :n)"
            ),
            {"c": now, "u": now, "n": code},
        )


def _create_asset_tables(asset_status: PG_ENUM, attachment_type: PG_ENUM) -> None:
    op.create_table(
        "assets",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("subcategory", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(120), nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("serial_number", sa.String(120), nullable=True),
        sa.Column("patrimony_tag", sa.String(64), nullable=True),
        sa.Column("imei", sa.String(32), nullable=True),
        sa.Column("ca_number", sa.String(64), nullable=True),
        sa.Column("status", asset_status, nullable=False, server_default="AVAILABLE"),
        sa.Column("acquisition_date", sa.Date(), nullable=True),
        sa.Column("acquisition_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cost_center", sa.String(255), nullable=True),
        sa.Column("cost_center_project_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("cost_center_system", sa.String(32), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["cost_center_project_id"], ["projects.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_assets_asset_code", "assets", ["asset_code"], unique=True)
    op.create_index("ix_assets_name", "assets", ["name"], unique=False)
    op.create_index("ix_assets_category", "assets", ["category"], unique=False)
    op.create_index("ix_assets_status", "assets", ["status"], unique=False)
    op.create_index("ix_assets_deleted_at", "assets", ["deleted_at"], unique=False)

    op.create_table(
        "asset_assignments",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("delivered_by_employee_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("received_by_employee_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("returned_by_employee_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("return_received_by_employee_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["delivered_by_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["received_by_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["returned_by_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["return_received_by_employee_id"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_asset_assignments_asset_id", "asset_assignments", ["asset_id"], unique=False)
    op.create_index("ix_asset_assignments_employee_id", "asset_assignments", ["employee_id"], unique=False)

    op.create_table(
        "asset_attachments",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", attachment_type, nullable=False, server_default="OTHER"),
        sa.Column("stored_path", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("uploaded_by_user_id", PG_UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_asset_attachments_asset_id", "asset_attachments", ["asset_id"], unique=False)

    op.create_table(
        "asset_inspections",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("inspection_type", sa.String(120), nullable=False),
        sa.Column("inspection_date", sa.Date(), nullable=False),
        sa.Column("expiration_months", sa.Integer(), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("responsible_company", sa.String(255), nullable=True),
        sa.Column("report_attachment_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_attachment_id"], ["asset_attachments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_asset_inspections_asset_id", "asset_inspections", ["asset_id"], unique=False)
    op.create_index("ix_asset_inspections_expiration_date", "asset_inspections", ["expiration_date"], unique=False)


def downgrade() -> None:
    op.drop_table("asset_inspections")
    op.drop_table("asset_attachments")
    op.drop_table("asset_assignments")
    op.drop_table("assets")
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM permissions WHERE name IN "
            "('workspace.assets.access', 'assets.view', 'assets.edit')"
        )
    )
    sa.Enum(name="asset_attachment_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="asset_status").drop(op.get_bind(), checkfirst=True)
