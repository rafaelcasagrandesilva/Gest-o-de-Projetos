"""project_labors: DROP IF EXISTS colunas legadas (reparo idempotente).

Revision ID: 0007_labors_repair
Revises: 0006_project_labor_employee_only
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_labors_repair"
down_revision = "0006_project_labor_employee_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM project_labors WHERE employee_id IS NULL"))
    for col in ("monthly_cost", "hours_per_month", "hourly_rate", "fixed_value", "labor_type"):
        op.execute(sa.text(f"ALTER TABLE project_labors DROP COLUMN IF EXISTS {col}"))

    op.alter_column(
        "project_labors",
        "employee_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.execute(sa.text("ALTER TABLE project_labors DROP CONSTRAINT IF EXISTS project_labors_employee_id_fkey"))
    op.create_foreign_key(
        "project_labors_employee_id_fkey",
        "project_labors",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        sa.text(
            """
            DO $body$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_project_labors_project_employee_competencia'
              ) THEN
                ALTER TABLE project_labors
                  ADD CONSTRAINT uq_project_labors_project_employee_competencia
                  UNIQUE (project_id, employee_id, competencia);
              END IF;
            END
            $body$;
            """
        )
    )


def downgrade() -> None:
    pass
