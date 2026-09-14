"""payables: remove os títulos legados de R$ 19.000 do endividamento "Aluguel do Instituto".

Os dois títulos foram gerados pelo VALOR DE REFERÊNCIA do cadastro (R$ 19.000) antes de a dívida
passar a ter lançamentos mês a mês na grade (hoje só 08/2026 e 09/2026, R$ 300 cada, e o item não é
"Obrigatório mensal"). Não correspondem a nenhuma obrigação real e não saíam pela tela: sem vínculo a
lançamento (`entry_id` NULL), a regra de orfandade os tratava como válidos enquanto o item existisse.

Lista FECHADA de ids (levantamento de 14/09/2026 sobre o backup de produção), nunca por nome:
    - 1412c967-4a48-40bc-ad38-ae20ed8991e3  07/2026  R$ 19.000,00
    - 1b00cba8-52a9-4d60-aa35-2d7853f3f30d  11/2027  R$ 19.000,00
Só apaga se ainda for ENDIVIDAMENTO sem vínculo a lançamento, sem valor pago e sem nenhum pagamento
registrado (nem estornado). Id ausente ou alterado desde o levantamento é ignorado.

IRREVERSÍVEL: o downgrade não recria os títulos.

Revision ID: 0143_remove_legacy_debt_payables_instituto
Revises: 0142_remove_legacy_vehicle_payables
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0143_remove_legacy_debt_payables_instituto"
down_revision = "0142_remove_legacy_vehicle_payables"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

LEGACY_DEBT_PAYABLE_IDS = (
    "1412c967-4a48-40bc-ad38-ae20ed8991e3",
    "1b00cba8-52a9-4d60-aa35-2d7853f3f30d",
)

_WHERE = """
    CAST(ps.id AS text) IN :ids
    AND ps.type = 'ENDIVIDAMENTO'
    AND ps.entry_id IS NULL
    AND COALESCE(ps.amount_paid, 0) = 0
    AND NOT EXISTS (SELECT 1 FROM payable_payments pp WHERE pp.payable_snapshot_id = ps.id)
"""


def upgrade() -> None:
    bind = op.get_bind()
    ids = sa.bindparam("ids", value=list(LEGACY_DEBT_PAYABLE_IDS), expanding=True)
    count, total = bind.execute(
        sa.text(f"SELECT count(*), COALESCE(sum(ps.amount_final), 0) FROM payable_snapshots ps WHERE {_WHERE}").bindparams(ids)
    ).one()
    bind.execute(sa.text(f"DELETE FROM payable_snapshots ps WHERE {_WHERE}").bindparams(ids))
    log.info("0143: removidos %s título(s) legado(s) do Aluguel do Instituto (R$ %.2f)", count, total)


def downgrade() -> None:
    # Irreversível: títulos legados removidos não são recriados.
    pass
