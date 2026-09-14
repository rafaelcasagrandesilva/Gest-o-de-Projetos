"""payables: "Custo direto do projeto" nos lançamentos MANUAIS do Contas a Pagar.

- Acrescenta 'DIRETO' ao CHECK `ck_payable_snapshots_result_classification`.
- Adiciona `result_project_id` UUID NULL (FK projects, ON DELETE SET NULL): o projeto ATIVO do centro
  de custo em que o lançamento soma como custo direto no Resultado da Empresa. Coluna própria de
  propósito — `project_id` do título governa acesso por projeto e as sincronizações do CAP, que não
  devem mudar por causa da classificação.
- CHECK `ck_payable_snapshots_result_direct_project`: 'DIRETO' exige o projeto.

Sem carga de dados.

Revision ID: 0141_manual_result_direct
Revises: 0140_manual_result_classification
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0141_manual_result_direct"
down_revision = "0140_manual_result_classification"
branch_labels = None
depends_on = None

_CLASSIFICATION_CHECK = "ck_payable_snapshots_result_classification"
_DIRECT_PROJECT_CHECK = "ck_payable_snapshots_result_direct_project"
_FK = "fk_payable_snapshots_result_project_id_projects"


def upgrade() -> None:
    op.add_column("payable_snapshots", sa.Column("result_project_id", PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(_FK, "payable_snapshots", "projects", ["result_project_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_payable_snapshots_result_project_id", "payable_snapshots", ["result_project_id"])
    op.drop_constraint(_CLASSIFICATION_CHECK, "payable_snapshots", type_="check")
    op.create_check_constraint(
        _CLASSIFICATION_CHECK,
        "payable_snapshots",
        "result_classification IS NULL OR result_classification IN ('DIRETO', 'INDIRETO', 'ENDIVIDAMENTO', 'FORA')",
    )
    op.create_check_constraint(
        _DIRECT_PROJECT_CHECK,
        "payable_snapshots",
        "result_classification IS DISTINCT FROM 'DIRETO' OR result_project_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_DIRECT_PROJECT_CHECK, "payable_snapshots", type_="check")
    op.execute("UPDATE payable_snapshots SET result_classification = NULL WHERE result_classification = 'DIRETO'")
    op.drop_constraint(_CLASSIFICATION_CHECK, "payable_snapshots", type_="check")
    op.create_check_constraint(
        _CLASSIFICATION_CHECK,
        "payable_snapshots",
        "result_classification IS NULL OR result_classification IN ('INDIRETO', 'ENDIVIDAMENTO', 'FORA')",
    )
    op.drop_index("ix_payable_snapshots_result_project_id", table_name="payable_snapshots")
    op.drop_constraint(_FK, "payable_snapshots", type_="foreignkey")
    op.drop_column("payable_snapshots", "result_project_id")
