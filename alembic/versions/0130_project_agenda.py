"""Agenda do workspace Projetos: compromissos, participantes e anexos (a ata).

Cria o módulo pedido pela gestão: marcar reuniões e **atribuir obrigações a responsáveis com
prazo**, com a ata anexada ao próprio compromisso. Ver docs/ETAPA0_AGENDA_PROJETOS.md.

**Totalmente separada da agenda do Jurídico**, por decisão de produto: tabelas próprias,
vocabulário próprio (REUNIAO/OBRIGACAO/EVENTO/PRAZO/VISITA — nada de Audiência ou Perícia) e
permissões próprias. Nenhum registro de uma agenda aparece na outra, e nada do módulo Jurídico é
tocado por esta migration.

Responsável e participantes são USUÁRIOS: as pessoas que a gestão citou já têm login, e o
vínculo real é o que permite cada um abrir o sistema e ver o que lhe foi atribuído. Para quem não
tem acesso existe o campo livre `external_participants`.

Anexos guardam só metadados; o arquivo mora no volume sob `STORAGE_ROOT`, como os PDFs de NF.

Permissões: recurso `project_agenda` (list/read/create/update/delete), concedido aos perfis que
já administram Projetos (quem tem `projects.create`) e a `system.admin`. Perfil somente-leitura
recebe apenas `list`/`read`, para enxergar a agenda sem poder marcar nada.

Exclusivamente ADITIVA — nenhuma tabela ou permissão existente é alterada.

Revision ID: 0130_project_agenda
Revises: 0129_purge_repasse_reversed_entries
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0130_project_agenda"
down_revision = "0129_purge_repasse_reversed_entries"
branch_labels = None
depends_on = None

_WRITE_CODES = ("project_agenda.create", "project_agenda.update", "project_agenda.delete")
_READ_CODES = ("project_agenda.list", "project_agenda.read")
_ALL_CODES = _READ_CODES + _WRITE_CODES


def upgrade() -> None:
    op.create_table(
        "project_commitments",
        # id e timestamps vêm da aplicação (TimestampUUIDMixin), como nas demais tabelas.
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # `starts_at` = o que acontece numa hora; `due_at` = o que precisa estar entregue.
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("modality", sa.String(16), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_participants", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="AGENDADO"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_note", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Projeto e responsável somem sem levar o compromisso junto: a reunião aconteceu.
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    for col in ("kind", "starts_at", "due_at", "project_id", "owner_user_id", "status"):
        op.create_index(f"ix_project_commitments_{col}", "project_commitments", [col])

    op.create_table(
        "project_commitment_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("commitment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["commitment_id"], ["project_commitments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("commitment_id", "user_id", name="uq_project_commitment_participant"),
    )
    op.create_index(
        "ix_project_commitment_participants_commitment_id",
        "project_commitment_participants",
        ["commitment_id"],
    )
    op.create_index(
        "ix_project_commitment_participants_user_id", "project_commitment_participants", ["user_id"]
    )

    op.create_table(
        "project_commitment_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("commitment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        # Marca a ATA entre os demais documentos, sem precisar de outra tabela.
        sa.Column("is_minutes", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["commitment_id"], ["project_commitments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_project_commitment_attachments_commitment_id",
        "project_commitment_attachments",
        ["commitment_id"],
    )

    conn = op.get_bind()
    for name in _ALL_CODES:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, created_at, updated_at, name) "
                "VALUES (gen_random_uuid(), now(), now(), :n) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": name},
        )

    # Escrita: perfis que já EDITAM projeto (`projects.update`) + system.admin. A regra é
    # `update`, e não `create`: o GESTOR — justamente quem marca reunião e atribui obrigação —
    # edita projeto mas não cria, e com `create` ficaria só com leitura da própria agenda.
    for name in _WRITE_CODES:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), r.role_id, np.id FROM ("
                "  SELECT rp.role_id FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id"
                "   WHERE p.name IN ('projects.update', 'system.admin') GROUP BY rp.role_id"
                ") r JOIN permissions np ON np.name = :new "
                "WHERE NOT EXISTS (SELECT 1 FROM role_permissions x "
                "                   WHERE x.role_id = r.role_id AND x.permission_id = np.id)"
            ),
            {"new": name},
        )

    # Leitura: qualquer perfil que já enxerga Projetos vê a agenda (sem poder marcar nada) —
    # inclusive o somente-leitura CONSULTA, que tem `projects.read` sem `list` na tabela.
    for name in _READ_CODES:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (id, created_at, updated_at, role_id, permission_id) "
                "SELECT gen_random_uuid(), now(), now(), r.role_id, np.id FROM ("
                "  SELECT rp.role_id FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id"
                "   WHERE p.name IN ('projects.read', 'projects.list', 'projects.view', 'system.admin') GROUP BY rp.role_id"
                ") r JOIN permissions np ON np.name = :new "
                "WHERE NOT EXISTS (SELECT 1 FROM role_permissions x "
                "                   WHERE x.role_id = r.role_id AND x.permission_id = np.id)"
            ),
            {"new": name},
        )

    concedidas = conn.execute(
        sa.text(
            "SELECT p.name, count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id"
            " WHERE p.name = ANY(:codes) GROUP BY p.name ORDER BY p.name"
        ),
        {"codes": list(_ALL_CODES)},
    ).all()
    for nome, qtd in concedidas:
        print(f"[0130] {nome}: concedida a {qtd} perfil(is).")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE name = ANY(:codes))"
        ),
        {"codes": list(_ALL_CODES)},
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE name = ANY(:codes)"), {"codes": list(_ALL_CODES)})
    op.drop_table("project_commitment_attachments")
    op.drop_table("project_commitment_participants")
    op.drop_table("project_commitments")
