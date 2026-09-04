"""Regra única de "NF FATURADA" e a soma faturada por projeto/competência.

Uma nota entra no faturamento quando é **oficial** e **não está cancelada**:

- `is_official = false` é a PRÉ-FATURADA — ainda não é faturamento firme e fica de fora,
  mesmo representando valor relevante;
- `CANCELADA` sai por motivo óbvio;
- `EMITIDA`, `ANTECIPADA` e `RECEBIDA` contam igual: antecipar ou receber não desfaz o
  faturamento, apenas descreve o que aconteceu com o dinheiro depois.

Regra definida em 01/09/2026 para o consumo de contrato e reaproveitada aqui para a
conciliação do Faturamento — daí morar num módulo próprio, em vez de existir uma cópia em
cada serviço que precisa dela.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receivable import ReceivableInvoice


def billed_invoice_filter() -> list[ColumnElement[bool]]:
    """Condições que definem uma NF faturada. Use com `*billed_invoice_filter()`."""
    return [
        ReceivableInvoice.is_official.is_(True),
        ReceivableInvoice.invoice_status != "CANCELADA",
    ]


def invoice_competencia_column() -> ColumnElement[date]:
    """Competência da NF — `competence_month`, sem fallback.

    NÃO derivar do mês da emissão: a NF é emitida cerca de um mês DEPOIS do serviço (das 9
    notas de competência 07/2026 de Fiscalização AT, 7 foram emitidas em agosto), então o mês
    da emissão jogaria a nota para a competência seguinte e a conciliação compararia meses
    trocados. Errar para menos é visível; errar de mês é silencioso.

    Notas sem competência preenchida ficam FORA da conciliação — `competence_month` só passou a
    ser obrigatório em NFs novas. Quem consome esta função deve avisar quantas ficaram de fora
    (ver `uncompetenced_invoice_counts`), senão o mês aparece com soma menor sem explicar por quê.
    """
    return ReceivableInvoice.competence_month


async def billed_totals_by_competencia(
    db: AsyncSession,
    *,
    project_ids: list[UUID] | None = None,
    competencias: list[date] | None = None,
) -> dict[tuple[UUID, date], float]:
    """Soma do BRUTO das NFs faturadas, agrupada por (projeto, competência).

    Uma única consulta agrupada — os chamadores costumam precisar de vários meses de uma vez
    (a listagem de Faturamento, o Dashboard), e uma consulta por linha seria custosa.
    """
    comp = invoice_competencia_column().label("competencia")
    stmt = (
        select(
            ReceivableInvoice.project_id,
            comp,
            func.coalesce(func.sum(ReceivableInvoice.gross_amount), 0),
        )
        .where(*billed_invoice_filter(), comp.is_not(None))
        .group_by(ReceivableInvoice.project_id, comp)
    )
    if project_ids:
        stmt = stmt.where(ReceivableInvoice.project_id.in_(project_ids))
    if competencias:
        stmt = stmt.where(comp.in_(competencias))
    rows = (await db.execute(stmt)).all()
    return {(r[0], r[1]): float(r[2] or 0) for r in rows}


async def uncompetenced_invoice_counts(
    db: AsyncSession, *, project_ids: list[UUID] | None = None
) -> dict[UUID, tuple[int, float]]:
    """Por projeto, quantas NFs faturadas estão sem competência e quanto somam.

    São notas que a conciliação não consegue atribuir a mês nenhum, então ficam fora da
    comparação. Sem esse aviso na tela, o mês apareceria com soma menor e a divergência
    seria lida como erro do gestor.
    """
    stmt = (
        select(
            ReceivableInvoice.project_id,
            func.count(),
            func.coalesce(func.sum(ReceivableInvoice.gross_amount), 0),
        )
        .where(*billed_invoice_filter(), ReceivableInvoice.competence_month.is_(None))
        .group_by(ReceivableInvoice.project_id)
    )
    if project_ids:
        stmt = stmt.where(ReceivableInvoice.project_id.in_(project_ids))
    rows = (await db.execute(stmt)).all()
    return {r[0]: (int(r[1]), float(r[2] or 0)) for r in rows}
