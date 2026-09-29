"""Jurídico — multa do art. 477 sai das Observações e vai para o campo próprio.

Antes da 0151 a multa era anotada à mão nas Observações do desligado ("Tem multa do 477 -
3.060,14", "Multa Art. 477 - 1.893,64"). Esta migration lê esse texto com a MESMA regra do
importador (`split_art477_fine`) e:

- grava o valor em `art477_fine` — só quando o campo está vazio (valor já cadastrado na tela
  nunca é sobrescrito);
- tira o trecho da multa das Observações (o resto da observação é preservado; se não sobrar
  nada, a observação fica vazia);
- registra as duas alterações no histórico do desligado (`legal_change_logs`), marcadas com
  `changed_by_email = 'migracao-0153'`.

Idempotente: numa segunda execução não há mais multa nas Observações.
Reversível: o downgrade devolve os valores anteriores a partir do próprio histórico.

Revision ID: 0153_legal_art477_from_notes
Revises: 0152_legal_person_documents
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

from app.services.legal_import_parser import split_art477_fine

revision = "0153_legal_art477_from_notes"
down_revision = "0152_legal_person_documents"
branch_labels = None
depends_on = None

MARKER = "migracao-0153"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, notes FROM legal_persons "
            "WHERE art477_fine IS NULL AND notes ~* 'multa' AND notes ~ '477'"
        )
    ).all()
    now = datetime.now(timezone.utc)
    insert_log = sa.text(
        "INSERT INTO legal_change_logs "
        "(id, created_at, updated_at, entity_type, entity_id, action, field, old_value, "
        " new_value, changed_by_email) "
        "VALUES (:id, :now, :now, 'PERSON', :entity_id, 'UPDATE', :field, :old, :new, :marker)"
    )
    for person_id, notes in rows:
        fine, rest = split_art477_fine(notes)
        if fine is None:
            continue
        bind.execute(
            sa.text("UPDATE legal_persons SET art477_fine = :fine, notes = :notes, updated_at = :now WHERE id = :id"),
            {"fine": Decimal(f"{fine:.2f}"), "notes": rest, "now": now, "id": person_id},
        )
        for field, old, new in (("art477_fine", None, f"{fine:.2f}"), ("notes", notes, rest)):
            bind.execute(
                insert_log,
                {"id": uuid4(), "now": now, "entity_id": person_id, "field": field,
                 "old": old, "new": new, "marker": MARKER},
            )


def downgrade() -> None:
    bind = op.get_bind()
    logs = bind.execute(
        sa.text(
            "SELECT entity_id, field, old_value FROM legal_change_logs "
            "WHERE changed_by_email = :marker"
        ),
        {"marker": MARKER},
    ).all()
    for person_id, field, old in logs:
        if field == "notes":
            bind.execute(sa.text("UPDATE legal_persons SET notes = :old WHERE id = :id"),
                         {"old": old, "id": person_id})
        elif field == "art477_fine":
            bind.execute(sa.text("UPDATE legal_persons SET art477_fine = NULL WHERE id = :id"),
                         {"id": person_id})
    bind.execute(sa.text("DELETE FROM legal_change_logs WHERE changed_by_email = :marker"),
                 {"marker": MARKER})
