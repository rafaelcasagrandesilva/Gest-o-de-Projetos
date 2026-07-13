"""Centro de Custo temporal (histórico) — colaboradores e veículos.

Torna o Centro de Custo um atributo temporal: a fonte da verdade passa a ser o histórico
(`employee_cost_center_history` / `vehicle_cost_center_history`). Os campos
`employees.cost_center` / `vehicles.cost_center` permanecem apenas como CACHE do centro
vigente. Regra: nunca sobrescrever histórico — sempre fechar a linha anterior e abrir nova.

100% ADITIVA:
- add_column `vehicles.cost_center` (novo; nullable).
- create_table das 2 tabelas de histórico (índice por (entidade, start_date)).
- BACKFILL idempotente: para cada colaborador/veículo SEM histórico, cria a linha inicial
  (cost_center = valor atual do cache, start_date = 1900-01-01, end_date = NULL). Assim todos
  continuam válidos "desde sempre" e o comportamento atual é preservado.

Nenhuma tabela/coluna existente é alterada (além do add_column) e NENHUM UPDATE destrutivo.

Revision ID: 0089_cost_center_history
Revises: 0088_backfill_project_cost_center
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from alembic import op

revision = "0089_cost_center_history"
down_revision = "0088_backfill_project_cost_center"
branch_labels = None
depends_on = None


def _history_table(name: str, fk_col: str, fk_table: str, index_name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            fk_col,
            PG_UUID(as_uuid=True),
            sa.ForeignKey(f"{fk_table}.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("cost_center", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(index_name, name, [fk_col, "start_date"], unique=False)


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("cost_center", sa.String(length=255), nullable=True))
    op.create_index("ix_vehicles_cost_center", "vehicles", ["cost_center"], unique=False)

    _history_table(
        "employee_cost_center_history",
        "employee_id",
        "employees",
        "ix_employee_cost_center_history_employee_start",
    )
    _history_table(
        "vehicle_cost_center_history",
        "vehicle_id",
        "vehicles",
        "ix_vehicle_cost_center_history_vehicle_start",
    )

    # Backfill: linha inicial "desde 1900" para quem ainda não tem histórico (idempotente).
    op.execute(
        """
        INSERT INTO employee_cost_center_history (id, employee_id, cost_center, start_date, end_date, created_at, updated_at)
        SELECT gen_random_uuid(), e.id, e.cost_center, DATE '1900-01-01', NULL, now(), now()
          FROM employees e
         WHERE NOT EXISTS (
               SELECT 1 FROM employee_cost_center_history h WHERE h.employee_id = e.id
         );
        """
    )
    op.execute(
        """
        INSERT INTO vehicle_cost_center_history (id, vehicle_id, cost_center, start_date, end_date, created_at, updated_at)
        SELECT gen_random_uuid(), v.id, v.cost_center, DATE '1900-01-01', NULL, now(), now()
          FROM vehicles v
         WHERE NOT EXISTS (
               SELECT 1 FROM vehicle_cost_center_history h WHERE h.vehicle_id = v.id
         );
        """
    )


def downgrade() -> None:
    op.drop_index("ix_vehicle_cost_center_history_vehicle_start", table_name="vehicle_cost_center_history")
    op.drop_table("vehicle_cost_center_history")
    op.drop_index("ix_employee_cost_center_history_employee_start", table_name="employee_cost_center_history")
    op.drop_table("employee_cost_center_history")
    op.drop_index("ix_vehicles_cost_center", table_name="vehicles")
    op.drop_column("vehicles", "cost_center")
