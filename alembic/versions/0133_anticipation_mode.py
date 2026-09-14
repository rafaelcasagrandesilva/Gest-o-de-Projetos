"""Antecipação automática: modo de cálculo do custo de antecipação no motor financeiro.

`anticipation_mode`:
- AUTOMATICO (padrão): o custo sai dos borderôs, um mês à frente. O mês trabalhado M usa o
  custo REAL das operações de M+1 (Lepta + Daycoval, antecipado − creditado, sem o repasse) ÷
  receita realizada de M; sem operações ainda, previsto ou sem dado usa a média ponderada dos
  pares já fechados. Ver app/services/anticipation_rate.py.
- FIXO: volta ao comportamento anterior — `anticipation_rate` sobre a receita.

`anticipation_rate` continua existindo e guardado: é o valor do modo FIXO (a "volta" para o
percentual fixo) e o fallback quando ainda não há histórico de antecipações.

Exclusivamente ADITIVA.

Revision ID: 0133_anticipation_mode
Revises: 0132_commitment_series
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0133_anticipation_mode"
down_revision = "0132_commitment_series"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "anticipation_mode",
            sa.String(length=16),
            nullable=False,
            server_default="AUTOMATICO",
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "anticipation_mode")
