"""Corrige competência (month) de snapshots gerados com mês-fonte incorreto.

Revision ID: 0060_fix_payable_snapshot_competence
Revises: 0059_payable_payments
"""

from __future__ import annotations

import calendar
from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "0060_fix_payable_snapshot_competence"
down_revision = "0059_payable_payments"
branch_labels = None
depends_on = None

SOURCE_TAG_PROJECT_MISC = "[source:project_misc_cost]"
SOURCE_TAG_PROJECT_SYSTEM = "[source:project_system]"


def _normalize_competencia(value: date) -> date:
    return date(value.year, value.month, 1)


def _previous_competencia(comp: date) -> date:
    c = _normalize_competencia(comp)
    if c.month == 1:
        return date(c.year - 1, 12, 1)
    return date(c.year, c.month - 1, 1)


def _default_due_date(payment_month: date, *, day: int = 10) -> date:
    comp = _normalize_competencia(payment_month)
    last = calendar.monthrange(comp.year, comp.month)[1]
    return date(comp.year, comp.month, min(max(day, 1), last))


def upgrade() -> None:
    conn = op.get_bind()

    generations = [
        _normalize_competencia(row[0])
        for row in conn.execute(sa.text("SELECT month FROM payable_snapshot_generations")).fetchall()
    ]

    tagged_rows = conn.execute(
        sa.text(
            """
            SELECT id, month, due_date, observation
            FROM payable_snapshots
            WHERE type = 'FIXED_COST'
              AND ref_id IS NOT NULL
              AND project_id IS NOT NULL
              AND (
                observation = :misc_tag
                OR observation = :sys_tag
              )
            """
        ),
        {"misc_tag": SOURCE_TAG_PROJECT_MISC, "sys_tag": SOURCE_TAG_PROJECT_SYSTEM},
    ).fetchall()

    for row_id, row_month, _due_date, _observation in tagged_rows:
        row_comp = _normalize_competencia(row_month)
        if row_comp in generations:
            continue
        target: date | None = None
        for gen in generations:
            if row_comp == _previous_competencia(gen) and row_comp != gen:
                target = gen
                break
        if target is None:
            continue
        new_due = _default_due_date(target, day=10)
        conn.execute(
            sa.text(
                """
                UPDATE payable_snapshots
                SET month = :month, due_date = :due_date
                WHERE id = :id
                """
            ),
            {"id": row_id, "month": target, "due_date": new_due},
        )

    # Não alterar month a partir de due_date em massa: isso moveu competências legítimas
    # (ex.: obrigação JAN paga em MAI) e não é reversível com segurança em produção.


def downgrade() -> None:
    # Correção de dados; não há rollback seguro.
    pass
