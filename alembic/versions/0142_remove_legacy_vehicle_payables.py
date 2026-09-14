"""payables: remove os títulos legados de Veículos (type=VEHICLE) sem pagamento ativo.

A integração "veículos dos projetos → Contas a Pagar" foi descontinuada (nada mais cria títulos
VEHICLE). Os que sobraram só saíam na regeração do mês (`_purge_obsolete_vehicle_snapshots`), que é
bloqueada quando o mês tem lançamento automático pago — por isso ficaram presos no CAP (ex.: os 2
"Custo com veículos" de abril/2026, Fiscalização AT R$ 15.495,55 e Subterrâneo R$ 10.048,57, com
os pagamentos todos estornados).

Regra ESTRUTURAL (a mesma da limpeza da regeração), nunca por nome: apaga type='VEHICLE' com
amount_paid = 0 e sem pagamento ativo (payable_payments.reversed_at IS NULL). O histórico de
pagamentos estornados sai junto (ON DELETE CASCADE). Título de veículo com pagamento ativo é mantido.

IRREVERSÍVEL: o downgrade não recria os títulos.

Revision ID: 0142_remove_legacy_vehicle_payables
Revises: 0141_manual_result_direct
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0142_remove_legacy_vehicle_payables"
down_revision = "0141_manual_result_direct"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_WHERE = """
    ps.type = 'VEHICLE'
    AND COALESCE(ps.amount_paid, 0) = 0
    AND NOT EXISTS (
        SELECT 1 FROM payable_payments pp
        WHERE pp.payable_snapshot_id = ps.id AND pp.reversed_at IS NULL
    )
"""


def upgrade() -> None:
    bind = op.get_bind()
    count, total = bind.execute(
        sa.text(f"SELECT count(*), COALESCE(sum(ps.amount_final), 0) FROM payable_snapshots ps WHERE {_WHERE}")
    ).one()
    bind.execute(sa.text(f"DELETE FROM payable_snapshots ps WHERE {_WHERE}"))
    kept = bind.execute(sa.text("SELECT count(*) FROM payable_snapshots WHERE type = 'VEHICLE'")).scalar_one()
    log.info("0142: removidos %s título(s) de Veículos sem pagamento (R$ %.2f); mantidos com pagamento: %s", count, total, kept)


def downgrade() -> None:
    # Irreversível: títulos legados removidos não são recriados.
    pass
