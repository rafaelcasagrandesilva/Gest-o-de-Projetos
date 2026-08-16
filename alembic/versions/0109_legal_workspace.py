"""Workspace Jurídico (Fase 1) — Processos e Ex-colaboradores. Exclusivamente ADITIVA.

Cria:
- enums nativos `legal_case_status` e `legal_case_type`;
- `legal_persons`  — ex-colaborador (pessoa que pode estar vinculada a processos);
- `legal_cases`    — PROCESSO (entidade principal do módulo), com `person_id` OPCIONAL;
- os códigos de permissão do módulo (`legal.*` + `workspace.legal.access`) em `permissions`, e os
  semeia conforme o preset: ADMIN e GESTOR recebem CRUD completo + valores; CONSULTA recebe apenas
  leitura (list/read), SEM `legal.sensitive` — vê os processos sem valores.

Além dos perfis de sistema por NOME, semeia o conjunto completo em qualquer perfil (inclusive
CUSTOM) que já tenha `system.admin`. Motivo: em vários ambientes a administração real é feita por
um perfil custom (ex.: "SUPER ADMIN"), e semear só por nome deixaria o próprio administrador sem
enxergar o módulo novo. Como a autorização do sistema depende de PERMISSÃO e não de nome de perfil
(Fase 1), o critério aqui segue a mesma regra.

Demais perfis custom NÃO são semeados de propósito — o módulo é NOVO, não há acesso pré-existente a
preservar (diferente da 0098, onde o recurso já era acessível por outro código e semear era
necessário para não regredir). Um admin concede o Jurídico a esses perfis pela grade de permissões.

Não toca em nenhuma tabela, coluna, enum ou dado existente, e não altera `user_permissions`:
nenhum acesso atual muda.

Idempotente (`checkfirst` / `ON CONFLICT DO NOTHING`) e reversível (drop das tabelas/enums e das
permissões criadas aqui).

Revision ID: 0109_legal_workspace
Revises: 0108_settlement_events
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM

revision = "0109_legal_workspace"
down_revision = "0108_settlement_events"
branch_labels = None
depends_on = None

_WORKSPACE_CODE = "workspace.legal.access"
_READ_CODES: tuple[str, ...] = ("legal.reference", "legal.list", "legal.read")
_WRITE_CODES: tuple[str, ...] = ("legal.create", "legal.update", "legal.delete", "legal.sensitive")
_ALL_CODES: tuple[str, ...] = (_WORKSPACE_CODE, *_READ_CODES, *_WRITE_CODES)

# Perfil de sistema → códigos semeados (espelha ROLE_PRESET em app/core/permission_codes.py).
_ROLE_CODES: dict[str, tuple[str, ...]] = {
    "ADMIN": _ALL_CODES,
    "GESTOR": _ALL_CODES,
    "CONSULTA": (_WORKSPACE_CODE, *_READ_CODES),
}


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # create_type=False evita CREATE TYPE duplicado ao criar a tabela (após .create(checkfirst=True)).
    case_status = ENUM(
        "EM_ANDAMENTO",
        "COM_DECISAO",
        "SUSPENSO",
        "ACORDO",
        "ACORDO_FINALIZADO",
        "ENCERRADO",
        "SEM_PROCESSO",
        name="legal_case_status",
        create_type=False,
    )
    case_type = ENUM(
        "TRABALHISTA", "CIVEL", "TRIBUTARIO", "OUTRO", name="legal_case_type", create_type=False
    )
    case_status.create(bind, checkfirst=True)
    case_type.create(bind, checkfirst=True)

    # --- ex-colaboradores (criada ANTES: legal_cases a referencia) --------------------------
    if not insp.has_table("legal_persons"):
        op.create_table(
            "legal_persons",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("cpf", sa.String(length=20), nullable=True),
            sa.Column("company", sa.String(length=255), nullable=True),
            sa.Column("project", sa.String(length=255), nullable=True),
            sa.Column("client", sa.String(length=255), nullable=True),
            sa.Column("role", sa.String(length=120), nullable=True),
            sa.Column("admission_date", sa.Date(), nullable=True),
            sa.Column("termination_date", sa.Date(), nullable=True),
            sa.Column("severance_amount", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("fgts_balance", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cpf", name="uq_legal_persons_cpf"),
        )
        op.create_index("ix_legal_persons_full_name", "legal_persons", ["full_name"])
        op.create_index("ix_legal_persons_cpf", "legal_persons", ["cpf"])
        op.create_index("ix_legal_persons_company", "legal_persons", ["company"])
        op.create_index("ix_legal_persons_project", "legal_persons", ["project"])
        op.create_index("ix_legal_persons_client", "legal_persons", ["client"])
        op.create_index("ix_legal_persons_is_active", "legal_persons", ["is_active"])

    # --- processos (entidade principal) -----------------------------------------------------
    if not insp.has_table("legal_cases"):
        op.create_table(
            "legal_cases",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("case_number", sa.String(length=64), nullable=False),
            sa.Column("jusbrasil_url", sa.Text(), nullable=True),
            sa.Column("person_id", sa.Uuid(), nullable=True),
            sa.Column("status", case_status, nullable=False, server_default="EM_ANDAMENTO"),
            sa.Column("case_type", case_type, nullable=False, server_default="TRABALHISTA"),
            sa.Column("nature", sa.String(length=120), nullable=True),
            sa.Column("uf", sa.String(length=2), nullable=True),
            sa.Column("court", sa.String(length=32), nullable=True),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("company", sa.String(length=255), nullable=True),
            sa.Column("project", sa.String(length=255), nullable=True),
            sa.Column("client", sa.String(length=255), nullable=True),
            sa.Column("claimant_name", sa.String(length=255), nullable=True),
            sa.Column("defendant_name", sa.String(length=255), nullable=True),
            sa.Column("amount_claimed", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("amount_considered", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("amount_agreed", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("amount_paid", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("amount_pending", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("agreement_terms", sa.Text(), nullable=True),
            sa.Column("last_movement", sa.Text(), nullable=True),
            sa.Column("last_movement_date", sa.Date(), nullable=True),
            sa.Column("hearing_date", sa.Date(), nullable=True),
            sa.Column("distribution_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["person_id"], ["legal_persons.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("case_number", name="uq_legal_cases_case_number"),
        )
        op.create_index("ix_legal_cases_case_number", "legal_cases", ["case_number"])
        op.create_index("ix_legal_cases_person_id", "legal_cases", ["person_id"])
        op.create_index("ix_legal_cases_status", "legal_cases", ["status"])
        op.create_index("ix_legal_cases_case_type", "legal_cases", ["case_type"])
        op.create_index("ix_legal_cases_uf", "legal_cases", ["uf"])
        op.create_index("ix_legal_cases_court", "legal_cases", ["court"])
        op.create_index("ix_legal_cases_company", "legal_cases", ["company"])
        op.create_index("ix_legal_cases_project", "legal_cases", ["project"])
        op.create_index("ix_legal_cases_client", "legal_cases", ["client"])
        op.create_index("ix_legal_cases_claimant_name", "legal_cases", ["claimant_name"])
        op.create_index("ix_legal_cases_last_movement_date", "legal_cases", ["last_movement_date"])

    # --- permissões -------------------------------------------------------------------------
    for code in _ALL_CODES:
        bind.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), now(), now(), :n) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": code},
        )

    for role_name, codes in _ROLE_CODES.items():
        for code in codes:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                    "SELECT gen_random_uuid(), now(), now(), r.id, p.id "
                    "FROM roles r CROSS JOIN permissions p "
                    "WHERE r.name = :role AND p.name = :code "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"role": role_name, "code": code},
            )

    # Perfis ADMINISTRADORES por PERMISSÃO (têm system.admin), inclusive custom — ex.: "SUPER ADMIN".
    for code in _ALL_CODES:
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), r.id, np.id "
                "  FROM roles r "
                "  JOIN role_permissions rp ON rp.role_id = r.id "
                "  JOIN permissions ap ON ap.id = rp.permission_id AND ap.name = 'system.admin' "
                "  JOIN permissions np ON np.name = :code "
                " GROUP BY r.id, np.id "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"code": code},
        )


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE name = ANY(:codes))"
        ),
        {"codes": list(_ALL_CODES)},
    )
    bind.execute(
        sa.text(
            "DELETE FROM user_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE name = ANY(:codes))"
        ),
        {"codes": list(_ALL_CODES)},
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE name = ANY(:codes)"), {"codes": list(_ALL_CODES)})

    op.drop_table("legal_cases")
    op.drop_table("legal_persons")
    ENUM(name="legal_case_type").drop(bind, checkfirst=True)
    ENUM(name="legal_case_status").drop(bind, checkfirst=True)
