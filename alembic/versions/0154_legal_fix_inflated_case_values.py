"""Jurídico — corrige 2 processos com valor inflado ×100 pelo formulário antigo de edição.

O CaseForm antigo (corrigido no PR #32) tirava todos os pontos do número: 69250.19 virava
6925019.00. O histórico (`legal_change_logs`) mostra 5 processos atingidos em 09/09; 3 foram
corrigidos à mão na mesma hora, estes 2 ficaram:

    0100453-52.2024.5.01.0246   6.925.019,00 → 69.250,19
    0100330-69.2025.5.01.0262     530.448,00 → 53.044,80

Só valor da causa e valor considerado foram inflados (os valores originais estão no histórico).
Cada campo só é alterado se AINDA estiver exatamente no valor inflado — se alguém já corrigiu
pela tela, nada é tocado. Registra no histórico (`changed_by_email = 'migracao-0154'`); o
downgrade devolve o que a upgrade trocou.

Revision ID: 0154_legal_fix_inflated_case_values
Revises: 0153_legal_art477_from_notes
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0154_legal_fix_inflated_case_values"
down_revision = "0153_legal_art477_from_notes"
branch_labels = None
depends_on = None

MARKER = "migracao-0154"
FIELDS = ("amount_claimed", "amount_considered")
# número do processo → (valor inflado, valor correto)
FIXES: dict[str, tuple[Decimal, Decimal]] = {
    "0100453-52.2024.5.01.0246": (Decimal("6925019.00"), Decimal("69250.19")),
    "0100330-69.2025.5.01.0262": (Decimal("530448.00"), Decimal("53044.80")),
}


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    for case_number, (wrong, right) in FIXES.items():
        case_id = bind.execute(
            sa.text("SELECT id FROM legal_cases WHERE case_number = :n"), {"n": case_number}
        ).scalar()
        if case_id is None:
            continue
        for field in FIELDS:
            changed = bind.execute(
                sa.text(
                    f"UPDATE legal_cases SET {field} = :right, updated_at = :now "
                    f"WHERE id = :id AND {field} = :wrong"
                ),
                {"right": right, "wrong": wrong, "now": now, "id": case_id},
            ).rowcount
            if changed:
                bind.execute(
                    sa.text(
                        "INSERT INTO legal_change_logs "
                        "(id, created_at, updated_at, entity_type, entity_id, action, field, "
                        " old_value, new_value, changed_by_email) "
                        "VALUES (:id, :now, :now, 'CASE', :eid, 'UPDATE', :field, :old, :new, :m)"
                    ),
                    {"id": uuid4(), "now": now, "eid": case_id, "field": field,
                     "old": f"{wrong:.2f}", "new": f"{right:.2f}", "m": MARKER},
                )


def downgrade() -> None:
    bind = op.get_bind()
    logs = bind.execute(
        sa.text(
            "SELECT entity_id, field, old_value FROM legal_change_logs WHERE changed_by_email = :m"
        ),
        {"m": MARKER},
    ).all()
    for case_id, field, old in logs:
        if field in FIELDS:
            bind.execute(
                sa.text(f"UPDATE legal_cases SET {field} = :old WHERE id = :id"),
                {"old": Decimal(old), "id": case_id},
            )
    bind.execute(sa.text("DELETE FROM legal_change_logs WHERE changed_by_email = :m"), {"m": MARKER})
