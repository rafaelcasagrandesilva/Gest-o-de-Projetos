"""payables: "Entra no resultado como" nos lançamentos MANUAIS do Contas a Pagar.

Adiciona a coluna `result_classification` VARCHAR(20) NULL em `payable_snapshots`, com CHECK
`ck_payable_snapshots_result_classification` (NULL ou 'INDIRETO'/'ENDIVIDAMENTO'/'FORA').
Define como um lançamento avulso entra no Resultado da Empresa: custo indireto, endividamento ou
fora do resultado (repasse, retenção, bloqueio judicial…). NULL = não classificado (não entra).
Só tem significado em type='MANUAL' — os demais tipos têm o destino definido pelo cadastro.

Sem carga de dados: os lançamentos existentes são classificados pelo financeiro na tela.

Revision ID: 0140_manual_result_classification
Revises: 0139_project_cost_group
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0140_manual_result_classification"
down_revision = "0139_project_cost_group"
branch_labels = None
depends_on = None

_CHECK = "ck_payable_snapshots_result_classification"


def upgrade() -> None:
    op.add_column("payable_snapshots", sa.Column("result_classification", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        _CHECK,
        "payable_snapshots",
        "result_classification IS NULL OR result_classification IN ('INDIRETO', 'ENDIVIDAMENTO', 'FORA')",
    )


def downgrade() -> None:
    op.drop_constraint(_CHECK, "payable_snapshots", type_="check")
    op.drop_column("payable_snapshots", "result_classification")
