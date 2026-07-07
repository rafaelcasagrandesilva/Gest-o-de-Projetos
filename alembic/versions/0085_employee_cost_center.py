"""Colaborador: Centro de Custo próprio + flag de alocação compartilhada.

Adiciona:
  - employees.cost_center (texto, o Centro de Custo principal do colaborador — mesmo
    domínio de projects.cost_center: Administrativo, Financeiro, Fiscalização AT, …);
  - employees.can_allocate_other_cost_centers (bool, default false — quando true o
    colaborador aparece para qualquer projeto: diretores/gerentes/compartilhados).

Backfill (aditivo, seguro): infere o Centro de Custo dos colaboradores existentes pelo
CENTRO PREDOMINANTE no histórico de alocações (project_labors → projects.cost_center),
apenas quando ainda NULL. Colaboradores sem histórico permanecem NULL (preenchimento
forçado na edição). Nenhuma coluna existente é alterada e nenhum dado é removido.

Revision ID: 0085_employee_cost_center
Revises: 0084_payable_snapshot_origin
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0085_employee_cost_center"
down_revision = "0084_payable_snapshot_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("cost_center", sa.String(length=255), nullable=True))
    op.add_column(
        "employees",
        sa.Column(
            "can_allocate_other_cost_centers",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_employees_cost_center", "employees", ["cost_center"], unique=False)

    # Backfill: centro de custo predominante no histórico de alocações (só onde NULL).
    op.execute(
        """
        WITH ranked AS (
            SELECT pl.employee_id AS eid,
                   p.cost_center   AS cc,
                   ROW_NUMBER() OVER (
                       PARTITION BY pl.employee_id
                       ORDER BY COUNT(*) DESC, p.cost_center ASC
                   ) AS rn
            FROM project_labors pl
            JOIN projects p ON p.id = pl.project_id
            WHERE p.cost_center IS NOT NULL AND btrim(p.cost_center) <> ''
            GROUP BY pl.employee_id, p.cost_center
        )
        UPDATE employees e
        SET cost_center = r.cc
        FROM ranked r
        WHERE r.eid = e.id AND r.rn = 1 AND e.cost_center IS NULL;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_employees_cost_center", table_name="employees")
    op.drop_column("employees", "can_allocate_other_cost_centers")
    op.drop_column("employees", "cost_center")
