"""Alocação contratual do colaborador (1 pessoa → N contratos). Exclusivamente ADITIVA.

Cria `employee_assignments`: a camada CONTRATUAL acima de `project_labors`. Nenhuma tabela
existente é alterada e NENHUM cálculo muda — `project_labors` continua sendo o registro mensal que
alimenta Folha, Contas a Pagar, custos de projeto, dashboards e relatórios.

BACKFILL — "cada colaborador atual ganha uma Alocação com seus dados atuais":

1. Uma Alocação por par DISTINTO (colaborador, projeto) já existente em `project_labors`. É o
   retrato fiel de quem hoje está em qual contrato. Herda da linha MAIS RECENTE do par:
   percentual, cargo e os overrides de valor daquele projeto.
2. Classificação do tipo, a partir do dado real:
       allocation_percentage = 100  →  INDEPENDENTE  (contrato próprio; hoje 468 linhas)
       allocation_percentage < 100  →  RATEIO        (custo dividido; hoje 42 linhas)
   O tipo é DECLARATIVO: não entra em nenhuma conta. `effective_percent` devolve exatamente o
   percentual que já era aplicado, então a matemática permanece bit a bit idêntica.
3. Colaborador ATIVO sem nenhuma linha em `project_labors` ganha uma Alocação apenas com o seu
   Centro de Custo (sem projeto), para que todo mundo tenha ao menos uma — como pedido.

Tudo o que o backfill cria vem marcado com `is_backfilled = true`, para distinguir o que o sistema
deduziu do que alguém cadastrou.

Reversível: `drop_table` + `drop_type` (a tabela nasce vazia de cadastro manual).

Revision ID: 0112_employee_assignments
Revises: 0111_legal_granular_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM

revision = "0112_employee_assignments"
down_revision = "0111_legal_granular_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    alloc_type = ENUM(
        "INDEPENDENTE", "RATEIO", name="employee_allocation_type", create_type=False
    )
    status = ENUM("ATIVA", "ENCERRADA", name="employee_assignment_status", create_type=False)
    alloc_type.create(bind, checkfirst=True)
    status.create(bind, checkfirst=True)

    if not insp.has_table("employee_assignments"):
        op.create_table(
            "employee_assignments",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("employee_id", sa.Uuid(), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=True),
            sa.Column("cost_center", sa.String(length=255), nullable=True),
            sa.Column("allocation_type", alloc_type, nullable=False, server_default="INDEPENDENTE"),
            sa.Column("role_title", sa.String(length=255), nullable=True),
            sa.Column("salary_base", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("allowance", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("hours_per_month", sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column("employment_type", sa.String(length=10), nullable=True),
            sa.Column(
                "allocation_percent", sa.Numeric(precision=5, scale=2), nullable=False, server_default="100"
            ),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("status", status, nullable=False, server_default="ATIVA"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_backfilled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("employee_id", "project_id", "cost_center", "allocation_type", "status",
                    "start_date", "end_date"):
            op.create_index(f"ix_employee_assignments_{col}", "employee_assignments", [col])

    # ---------------------------------------------------------------------------------------
    # Backfill 1 — um vínculo por par (colaborador, projeto) presente em project_labors.
    # DISTINCT ON pega a linha mais recente do par (competência desc), que é o retrato atual.
    # ---------------------------------------------------------------------------------------
    bind.execute(
        sa.text(
            """
            INSERT INTO employee_assignments (
                id, created_at, updated_at, employee_id, project_id, cost_center,
                allocation_type, role_title, salary_base, allowance, hours_per_month,
                allocation_percent, start_date, status, is_backfilled
            )
            SELECT gen_random_uuid(), now(), now(), s.employee_id, s.project_id, s.cost_center,
                   CASE WHEN s.pct = 100 THEN 'INDEPENDENTE' ELSE 'RATEIO' END::employee_allocation_type,
                   s.role_title, s.salary_base, NULL, s.hours,
                   s.pct, s.first_comp, 'ATIVA'::employee_assignment_status, true
              FROM (
                SELECT DISTINCT ON (pl.employee_id, pl.project_id)
                       pl.employee_id,
                       pl.project_id,
                       e.cost_center                        AS cost_center,
                       pl.allocation_percentage             AS pct,
                       e.role_title                         AS role_title,
                       pl.cost_salary_base                  AS salary_base,
                       pl.cost_pj_hours_per_month           AS hours,
                       min(pl.competencia) OVER (PARTITION BY pl.employee_id, pl.project_id) AS first_comp
                  FROM project_labors pl
                  JOIN employees e ON e.id = pl.employee_id
                 ORDER BY pl.employee_id, pl.project_id, pl.competencia DESC
              ) s
            """
        )
    )

    # ---------------------------------------------------------------------------------------
    # Backfill 2 — colaborador ATIVO sem nenhuma linha de projeto: alocação só de Centro de Custo.
    # ---------------------------------------------------------------------------------------
    bind.execute(
        sa.text(
            """
            INSERT INTO employee_assignments (
                id, created_at, updated_at, employee_id, project_id, cost_center,
                allocation_type, role_title, salary_base, allocation_percent,
                start_date, status, is_backfilled
            )
            SELECT gen_random_uuid(), now(), now(), e.id, NULL, e.cost_center,
                   'INDEPENDENTE'::employee_allocation_type, e.role_title, e.salary_base, 100,
                   e.start_date, 'ATIVA'::employee_assignment_status, true
              FROM employees e
             WHERE e.is_active
               AND NOT EXISTS (SELECT 1 FROM project_labors pl WHERE pl.employee_id = e.id)
               AND NOT EXISTS (SELECT 1 FROM employee_assignments a WHERE a.employee_id = e.id)
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("employee_assignments")
    ENUM(name="employee_assignment_status").drop(bind, checkfirst=True)
    ENUM(name="employee_allocation_type").drop(bind, checkfirst=True)
