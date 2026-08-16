"""Jurídico Fase 2 — Administração: catálogos, baixa lógica e histórico. Exclusivamente ADITIVA.

Nada da Fase 1 é remodelado: `legal_cases`/`legal_persons` mantêm suas colunas e semântica, e
`company`/`project` continuam TEXTO nos processos (não viram FK). Cria:

- `legal_cases.is_active` (default true) — baixa LÓGICA. `legal_persons.is_active` já existia.
- `legal_companies` / `legal_projects` — cadastros de VOCABULÁRIO que alimentam combos e filtros
  (mesmo papel do Centro de Custo). Semeados a partir dos valores JÁ presentes nos processos e nas
  pessoas, para que nenhum filtro existente perca opção.
- `legal_change_logs` (+ enums) — histórico append-only, um registro por CAMPO alterado.

Reversível: `drop_column`/`drop_table`/`drop_type`. Idempotente (`checkfirst` / `IF NOT EXISTS` /
`ON CONFLICT DO NOTHING`), então roda sem risco sobre uma base já migrada.

Revision ID: 0110_legal_admin_catalogs
Revises: 0109_legal_workspace
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM

revision = "0110_legal_admin_catalogs"
down_revision = "0109_legal_workspace"
branch_labels = None
depends_on = None


def _has_column(insp, table: str, column: str) -> bool:
    return insp.has_table(table) and column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # --- baixa lógica do processo -----------------------------------------------------------
    if not _has_column(insp, "legal_cases", "is_active"):
        op.add_column(
            "legal_cases",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        op.create_index("ix_legal_cases_is_active", "legal_cases", ["is_active"])

    # --- catálogos (vocabulário dos filtros) -------------------------------------------------
    if not insp.has_table("legal_companies"):
        op.create_table(
            "legal_companies",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("cnpj", sa.String(length=24), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_legal_companies_name"),
        )
        op.create_index("ix_legal_companies_name", "legal_companies", ["name"])
        op.create_index("ix_legal_companies_is_active", "legal_companies", ["is_active"])

    if not insp.has_table("legal_projects"):
        op.create_table(
            "legal_projects",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("client", sa.String(length=255), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_legal_projects_name"),
        )
        op.create_index("ix_legal_projects_name", "legal_projects", ["name"])
        op.create_index("ix_legal_projects_client", "legal_projects", ["client"])
        op.create_index("ix_legal_projects_is_active", "legal_projects", ["is_active"])

    # --- histórico ---------------------------------------------------------------------------
    entity_type = ENUM(
        "PERSON", "CASE", "COMPANY", "PROJECT", name="legal_entity_type", create_type=False
    )
    change_action = ENUM(
        "CREATE", "UPDATE", "DEACTIVATE", "RESTORE", name="legal_change_action", create_type=False
    )
    entity_type.create(bind, checkfirst=True)
    change_action.create(bind, checkfirst=True)

    if not insp.has_table("legal_change_logs"):
        op.create_table(
            "legal_change_logs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("entity_type", entity_type, nullable=False),
            sa.Column("entity_id", sa.Uuid(), nullable=False),
            sa.Column("action", change_action, nullable=False),
            sa.Column("field", sa.String(length=64), nullable=True),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=True),
            sa.Column("changed_by_id", sa.Uuid(), nullable=True),
            sa.Column("changed_by_email", sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_legal_change_logs_entity_type", "legal_change_logs", ["entity_type"])
        op.create_index("ix_legal_change_logs_entity_id", "legal_change_logs", ["entity_id"])
        op.create_index("ix_legal_change_logs_action", "legal_change_logs", ["action"])

    # --- semeadura dos catálogos a partir do que JÁ está em uso ------------------------------
    # Sem isto, cadastrar empresas/projetos "do zero" faria os filtros existentes perderem opções.
    bind.execute(
        sa.text(
            "INSERT INTO legal_companies (id, created_at, updated_at, name, is_active) "
            "SELECT gen_random_uuid(), now(), now(), s.name, true FROM ("
            "  SELECT DISTINCT btrim(company) AS name FROM legal_cases "
            "   WHERE company IS NOT NULL AND btrim(company) <> '' "
            "  UNION "
            "  SELECT DISTINCT btrim(company) FROM legal_persons "
            "   WHERE company IS NOT NULL AND btrim(company) <> '' "
            ") s ON CONFLICT (name) DO NOTHING"
        )
    )
    # O cliente do projeto vem do próprio processo (ex.: "Energisa - C&M Naviraí" → "Energisa").
    bind.execute(
        sa.text(
            "INSERT INTO legal_projects (id, created_at, updated_at, name, client, is_active) "
            "SELECT gen_random_uuid(), now(), now(), s.name, s.client, true FROM ("
            "  SELECT btrim(project) AS name, max(btrim(client)) AS client "
            "    FROM legal_cases WHERE project IS NOT NULL AND btrim(project) <> '' "
            "   GROUP BY btrim(project) "
            ") s ON CONFLICT (name) DO NOTHING"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO legal_projects (id, created_at, updated_at, name, client, is_active) "
            "SELECT gen_random_uuid(), now(), now(), s.name, s.client, true FROM ("
            "  SELECT btrim(project) AS name, max(btrim(client)) AS client "
            "    FROM legal_persons WHERE project IS NOT NULL AND btrim(project) <> '' "
            "   GROUP BY btrim(project) "
            ") s ON CONFLICT (name) DO NOTHING"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    op.drop_table("legal_change_logs")
    ENUM(name="legal_change_action").drop(bind, checkfirst=True)
    ENUM(name="legal_entity_type").drop(bind, checkfirst=True)

    op.drop_table("legal_projects")
    op.drop_table("legal_companies")

    if _has_column(insp, "legal_cases", "is_active"):
        op.drop_index("ix_legal_cases_is_active", table_name="legal_cases")
        op.drop_column("legal_cases", "is_active")
