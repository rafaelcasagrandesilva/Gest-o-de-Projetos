"""system settings + project operational cost structure

Revision ID: 0003_settings_operational
Revises: 0002_enterprise_financial
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0003_settings_operational"
down_revision = "0002_enterprise_financial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tax_rate", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("overhead_rate", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("anticipation_rate", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("clt_charges_rate", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("vehicle_light_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("vehicle_pickup_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("vehicle_sedan_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("vr_value", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("fuel_ethanol", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("fuel_gasoline", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("fuel_diesel", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("consumption_light", sa.Numeric(10, 4), nullable=False, server_default="1"),
        sa.Column("consumption_pickup", sa.Numeric(10, 4), nullable=False, server_default="1"),
        sa.Column("consumption_sedan", sa.Numeric(10, 4), nullable=False, server_default="1"),
    )

    op.create_table(
        "project_labors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("labor_type", sa.String(length=20), nullable=False),
        sa.Column("fixed_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("hourly_rate", sa.Numeric(14, 4), nullable=True),
        sa.Column("hours_per_month", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_cost", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_project_labors_competencia", "project_labors", ["competencia"], unique=False)
    op.create_index("ix_project_labors_project_id", "project_labors", ["project_id"], unique=False)

    op.create_table(
        "project_vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("vehicle_type", sa.String(length=20), nullable=False),
        sa.Column("fuel_type", sa.String(length=20), nullable=False),
        sa.Column("km_per_month", sa.Numeric(14, 2), nullable=False),
        sa.Column("monthly_cost", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_project_vehicles_competencia", "project_vehicles", ["competencia"], unique=False)
    op.create_index("ix_project_vehicles_project_id", "project_vehicles", ["project_id"], unique=False)

    op.create_table(
        "project_system_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_project_system_costs_competencia", "project_system_costs", ["competencia"], unique=False)
    op.create_index("ix_project_system_costs_project_id", "project_system_costs", ["project_id"], unique=False)

    op.create_table(
        "project_operational_fixed",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index(
        "ix_project_operational_fixed_competencia", "project_operational_fixed", ["competencia"], unique=False
    )
    op.create_index(
        "ix_project_operational_fixed_project_id", "project_operational_fixed", ["project_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_project_operational_fixed_project_id", table_name="project_operational_fixed")
    op.drop_index("ix_project_operational_fixed_competencia", table_name="project_operational_fixed")
    op.drop_table("project_operational_fixed")

    op.drop_index("ix_project_system_costs_project_id", table_name="project_system_costs")
    op.drop_index("ix_project_system_costs_competencia", table_name="project_system_costs")
    op.drop_table("project_system_costs")

    op.drop_index("ix_project_vehicles_project_id", table_name="project_vehicles")
    op.drop_index("ix_project_vehicles_competencia", table_name="project_vehicles")
    op.drop_table("project_vehicles")

    op.drop_index("ix_project_labors_project_id", table_name="project_labors")
    op.drop_index("ix_project_labors_competencia", table_name="project_labors")
    op.drop_table("project_labors")

    op.drop_table("system_settings")
