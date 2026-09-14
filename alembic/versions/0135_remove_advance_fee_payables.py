"""Antecipações: deságio e tarifas saem do Contas a Pagar.

Regra nova (código): nenhuma operação de antecipação gera título de deságio/tarifa no CAP — os
valores já vêm descontados do valor creditado (líquido = antecipados − deságio − tarifas), não há
o que pagar. O custo continua registrado na própria operação (discount_amount/fee_amount).

Esta migration remove o que já foi lançado (decisão do usuário, 2026-09-14):

1. TODOS os títulos automáticos `ANTECIPACAO_OPERACAO` ("Deságio • SGC n" / "Tarifas • SGC n",
   ref_id = operação). No banco de referência: 38 títulos, R$ 644.073,28 — inclusive os 2 da
   SGC 26 com pagamento registrado em 07/08/2026 (R$ 79.106,44).
2. Lançamentos MANUAIS equivalentes, por lista FECHADA de ids (nunca por nome/categoria — regra
   do CAP de não classificar título por texto), e só se ainda forem do tipo MANUAL:
   - 8 de julho/2026 "OP LEPTA - DESAGIO/TARIFAS" (R$ 90.122,94), digitados em 22/07;
   - 35 de jan–jun/2026 importados do extrato: deságio, desconto de duplicatas, juros (inclusive
     prorrogação 45dd) e tarifas bancárias DOC/TED/PIX (R$ 387.619,23).
   Um id ausente neste banco é simplesmente ignorado.

Os pagamentos desses títulos (`payable_payments`) saem junto (ON DELETE CASCADE).

IRREVERSÍVEL: o downgrade não recria os títulos nem os pagamentos.

Revision ID: 0135_remove_advance_fee_payables
Revises: 0134_company_result_permissions
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0135_remove_advance_fee_payables"
down_revision = "0134_company_result_permissions"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

MANUAL_FEE_PAYABLE_IDS: tuple[str, ...] = (
    # jan–jun/2026 — extrato importado: tarifas bancárias, deságio, desconto de duplicatas, juros
    "d196323e-019a-4193-9fd5-392bf09d4d5c",
    "82a78226-2421-4f00-a133-e4d2304fc847",
    "f202ba79-6152-4558-b722-b5ab2e5ae7f1",
    "6f43dc76-5ae7-4f6f-b002-c72a7575c360",
    "002dec02-76f2-4675-946d-a76d63744656",
    "87638dd4-609e-4eb2-ad34-31ec70e0473a",
    "c05aefc9-6529-4c62-9504-7773471a59bc",
    "e9986889-8c84-4735-b9c4-e13ddd660ec6",
    "414a02ed-4d80-4cdb-92f8-287e0ffeee07",
    "dbbd43e0-609c-4963-b131-b96e5c9f8356",
    "fbd4006f-88ca-48be-a1f1-86f5018584d3",
    "d7f679a8-062e-4b2a-a484-4d6ac5716b75",
    "acb0f454-d7c2-4a67-8624-40f81cca7d27",
    "a74489b3-635d-43eb-b34e-05bd7d54cf74",
    "eb6d24e9-8c27-4433-991e-e8ebf83ce456",
    "e3261efe-bbb9-412e-b331-5cbc88023e49",
    "1ec0a787-8f4a-40ed-8c15-a536474a1843",
    "d4d8f520-0278-48c6-a906-fa739250749c",
    "708c2cc1-7c13-4bd3-8842-f14045f20f6a",
    "378d212d-db59-4a40-bd69-24d36942aa67",
    "17087d13-80f3-4b6e-acd9-4a0912580b54",
    "84025c05-8af0-42c9-8ea5-9af034f54c5e",
    "29a89264-4b75-48ba-be99-95d271177904",
    "17f10e3b-7844-4bb9-be66-c970734f78ac",
    "d4a1545a-e26d-47f6-8248-eddff82e56e9",
    "d01ca6db-ec49-46ae-b2b5-f4b5ddb11119",
    "c7bddba3-9700-41b2-a82c-7c39248be98f",
    "0a27fc66-4594-4854-8cf4-da4748001c46",
    "0515d96b-e5fd-46b4-bd7b-1f4b3d77b840",
    "d5213777-0342-411f-9acc-0ae3ea387be6",
    "4b5a4eef-84fa-4c81-b1f4-db398a1e5e19",
    "deff8b7b-1ea9-4c1f-a140-7c8b44da800c",
    "3b606486-f398-4bd5-866b-e371e5026f0a",
    "0dc7f2d0-9a24-41bb-b4d1-811fd062e466",
    "099facf8-57fd-42c6-aa0f-d7987ae612a3",
    # jul/2026 — "OP LEPTA - DESAGIO" / "OP LEPTA - TARIFAS" digitados à mão
    "0137d7d8-9ca3-4ffd-86c8-5d86ba4f69de",
    "8d21ee4d-b8be-424b-b937-0b73a27bcc07",
    "d507c745-1479-43ca-b36f-ed2a83389937",
    "4eb9e8bb-5ebd-43ec-ac88-978e8cf3b1b0",
    "4df4f57f-844d-427b-8e9e-e176731439da",
    "f8420e17-51ea-480c-a8d3-91b00eef8667",
    "8c621e60-9f7b-4ec1-83cd-2dc1d518870d",
    "94e4ce6e-fd57-4267-a561-32d621799b9e",
)

_AUTO_WHERE = "type = 'ANTECIPACAO_OPERACAO'"
_MANUAL_WHERE = "type = 'MANUAL' AND id = ANY(CAST(:ids AS uuid[]))"


def _summary(conn, where: str, params: dict) -> tuple[int, float, int]:
    row = conn.execute(
        sa.text(
            f"SELECT count(*), coalesce(sum(amount_final), 0), "
            f"(SELECT count(*) FROM payable_payments p WHERE p.payable_snapshot_id IN "
            f"(SELECT id FROM payable_snapshots WHERE {where})) "
            f"FROM payable_snapshots WHERE {where}"
        ),
        params,
    ).one()
    return int(row[0]), float(row[1]), int(row[2])


def upgrade() -> None:
    conn = op.get_bind()
    params = {"ids": list(MANUAL_FEE_PAYABLE_IDS)}

    auto = _summary(conn, _AUTO_WHERE, {})
    manual = _summary(conn, _MANUAL_WHERE, params)
    logger.info(
        "Removendo deságio/tarifas do CAP: automáticos=%s títulos R$ %.2f (%s pagamentos); "
        "manuais=%s títulos R$ %.2f (%s pagamentos)",
        auto[0], auto[1], auto[2], manual[0], manual[1], manual[2],
    )

    conn.execute(sa.text(f"DELETE FROM payable_snapshots WHERE {_AUTO_WHERE}"))
    conn.execute(sa.text(f"DELETE FROM payable_snapshots WHERE {_MANUAL_WHERE}"), params)

    # Validação pós: nada do escopo pode sobrar (a transação da migration desfaz tudo se falhar).
    left_auto = _summary(conn, _AUTO_WHERE, {})[0]
    left_manual = _summary(conn, _MANUAL_WHERE, params)[0]
    if left_auto or left_manual:
        raise RuntimeError(
            f"Remoção incompleta: sobraram {left_auto} automáticos e {left_manual} manuais."
        )


def downgrade() -> None:
    # Irreversível: títulos e pagamentos removidos não são recriados.
    pass
