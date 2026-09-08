"""Limpeza pontual: remove os lançamentos ESTORNADOS do Ledger de Repasse.

O Ledger é append-only de propósito (nunca se edita nem se apaga; corrige-se estornando). Esta
migration é uma EXCEÇÃO explícita e única, a pedido do usuário: durante a carga inicial do saldo
de Repasse, em 08/09/2026, sete lançamentos foram estornados — três por erro de digitação até o
saldo fechar, e quatro pelo próprio sistema ao editar operações (SGC 14, 24 e 32). Nenhum deles
representa um evento financeiro real, e todos juntos poluíam a leitura do extrato.

**Não altera o saldo.** O saldo é `Σ CREDIT − Σ DEBIT dos lançamentos ATIVOS` — lançamento
estornado já estava fora da conta. Conferido no clone da produção antes e depois: R$ 45.855,11.

Remove por ID, e não por `reversed_at IS NOT NULL`: uma regra genérica apagaria também qualquer
estorno LEGÍTIMO feito entre a escrita desta migration e o deploy, que é justamente o tipo de
registro que o Ledger existe para guardar. Ausência de um id é tolerada (nada falha).

O que se perde: o rastro de que as operações SGC 14, 24 e 32 tiveram o valor do repasse alterado
depois de criadas. Decisão consciente do usuário — o de-para completo fica impresso no log deste
deploy.

Revision ID: 0129_purge_repasse_reversed_entries
Revises: 0128_repasse_withdrawal_debt_link
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0129_purge_repasse_reversed_entries"
down_revision = "0128_repasse_withdrawal_debt_link"
branch_labels = None
depends_on = None

# Os sete lançamentos, identificados no clone da produção de 08/09/2026 17:56.
ESTORNOS = (
    "44ec22a3-49bc-430d-a8e1-b981d60f3a67",  # 15/05 CREDIT 14.015,77 — SGC 14 (editar operação)
    "31d5c912-b003-4a0b-936e-0536bcd04295",  # 15/05 CREDIT 11.757,98 — SGC 14 (editar operação)
    "f9bb0f3a-7273-459a-9ff6-72045dae6f65",  # 05/06 DEBIT   5.261,61 — LQ-000013 (estorno manual)
    "117d2b18-2bca-4a3d-b2b7-b1e57ba91d6d",  # 08/06 DEBIT  29.398,70 — LQ-000012 (estorno manual)
    "dbf87b7a-e75e-4c11-8dca-49c56089ee2d",  # 15/06 DEBIT 215.522,92 — LQ-000016 (estorno manual)
    "d4c9f166-1e9a-4d82-8a82-5ad94c5b8df6",  # 14/08 CREDIT  1.600,78 — SGC 24 (editar operação)
    "543859f5-5f46-4e03-9615-db19eeb10c5f",  # 28/08 CREDIT  9.460,25 — SGC 32 (editar operação)
)


def _saldo(bind) -> str:
    return str(
        bind.execute(
            sa.text(
                "SELECT COALESCE(SUM(CASE WHEN direction = 'CREDIT' THEN amount ELSE -amount END), 0)"
                " FROM advance_repasse_ledger WHERE reversed_at IS NULL"
            )
        ).scalar_one()
    )


def upgrade() -> None:
    bind = op.get_bind()
    antes = _saldo(bind)

    # Só remove o que está estornado: um id que (por qualquer motivo) esteja ATIVO na produção
    # é um lançamento que conta no saldo, e apagá-lo mudaria o número.
    alvo = list(
        bind.execute(
            sa.text(
                "SELECT id, occurred_at, direction, amount, description"
                " FROM advance_repasse_ledger"
                " WHERE id = ANY(:ids) AND reversed_at IS NOT NULL"
                " ORDER BY occurred_at"
            ),
            {"ids": list(ESTORNOS)},
        )
    )
    print(f"[0129] Removendo {len(alvo)} lançamento(s) estornado(s) do Ledger de Repasse.")
    for row in alvo:
        print(f"[0129]   {row.occurred_at} {row.direction} {row.amount} — {row.description}")
    if len(alvo) != len(ESTORNOS):
        print(
            f"[0129] AVISO: {len(ESTORNOS) - len(alvo)} id(s) não encontrados ou já ativos — "
            "ignorados de propósito."
        )

    if alvo:
        bind.execute(
            sa.text("DELETE FROM advance_repasse_ledger WHERE id = ANY(:ids) AND reversed_at IS NOT NULL"),
            {"ids": [str(r.id) for r in alvo]},
        )

    depois = _saldo(bind)
    if antes != depois:
        raise RuntimeError(
            f"[0129] O saldo do Repasse mudou ({antes} -> {depois}) — abortando. "
            "Lançamento estornado não entra no saldo; se mudou, algo não era estorno."
        )
    print(f"[0129] Concluído. Saldo do Repasse inalterado: {depois}")


def downgrade() -> None:
    # Sem volta: os lançamentos foram removidos e não são reconstituíveis a partir de nenhum
    # outro dado. A reversão é o backup anterior à publicação.
    raise NotImplementedError(
        "0129 não tem downgrade: restaure o backup anterior à publicação."
    )
