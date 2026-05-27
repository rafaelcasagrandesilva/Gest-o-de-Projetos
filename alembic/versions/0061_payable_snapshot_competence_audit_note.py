"""Marcador: migration 0060 não deve reescrever competência em massa.

Se 0060 já rodou em produção com o UPDATE por due_date, restaure backup ou corrija
manualmente snapshots afetados — não há rollback automático seguro.

Revision ID: 0061_payable_snapshot_competence_audit_note
Revises: 0060_fix_payable_snapshot_competence
"""

from __future__ import annotations

revision = "0061_payable_snapshot_competence_audit_note"
down_revision = "0060_fix_payable_snapshot_competence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
