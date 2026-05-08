"""normalize revenues.competencia to month start

Revision ID: 0045_normalize_revenue_competencia
Revises: 0044_project_cost_center
Create Date: 2026-04-30

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0045_normalize_revenue_competencia"
down_revision = "0044_project_cost_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Garantir que `revenues.competencia` seja sempre o primeiro dia do mês.

    Motivo: dashboards/queries usam competência normalizada (YYYY-MM-01). Se o lançamento
    foi salvo com outro dia (ex.: YYYY-MM-20), o faturamento aparece como 0 no dashboard.

    Estratégia:
    - Normaliza competência via `date_trunc('month', competencia)::date`
    - Se isso gerar duplicatas pela chave única (project_id, competencia, description, scenario),
      consolida somando amount e mantém uma linha (menor id); remove as demais.
    """
    op.execute(
        sa.text(
            """
            WITH normalized AS (
              SELECT
                id,
                project_id,
                description,
                scenario,
                date_trunc('month', competencia)::date AS comp_month,
                amount,
                has_retention,
                status
              FROM revenues
            ),
            grp AS (
              SELECT
                project_id,
                description,
                scenario,
                comp_month,
                -- Em alguns ambientes, agregações MIN/MAX não existem para UUID.
                -- Usamos MIN(text) como "keep id" determinístico.
                MIN(id::text) AS keep_id,
                SUM(amount) AS amount_sum,
                BOOL_OR(has_retention) AS any_retention,
                BOOL_OR(status = 'recebido') AS any_received
              FROM normalized
              GROUP BY project_id, description, scenario, comp_month
            ),
            upd AS (
              UPDATE revenues r
              SET
                competencia = g.comp_month,
                amount = g.amount_sum,
                has_retention = g.any_retention,
                status = CASE WHEN g.any_received THEN 'recebido' ELSE 'previsto' END,
                updated_at = NOW()
              FROM grp g
              WHERE r.id::text = g.keep_id
              RETURNING r.id
            )
            DELETE FROM revenues r
            USING normalized n
            JOIN grp g
              ON g.project_id = n.project_id
             AND g.scenario = n.scenario
             AND g.comp_month = n.comp_month
             AND (
               (g.description IS NULL AND n.description IS NULL) OR
               (g.description IS NOT NULL AND n.description IS NOT NULL AND g.description = n.description)
             )
            WHERE r.id = n.id
              AND r.id::text <> g.keep_id;
            """
        )
    )


def downgrade() -> None:
    # Sem downgrade: a normalização é destrutiva (perde o "dia" original da competência).
    pass

