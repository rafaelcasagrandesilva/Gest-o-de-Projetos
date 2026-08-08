"""Ledger (extrato) de Repasse — módulo financeiro genérico e INDEPENDENTE.

Diretriz arquitetural: este serviço **nunca** conhece regras da LEPTA (nem de qualquer
instituição). Ele apenas **registra créditos e débitos** e responde o **saldo**. Quem decide
*quando* creditar/debitar é o fluxo de Antecipações (Liquidação/Operações) — que conversa com
este Ledger **somente** através da interface `RepasseLedgerPort` (`credit`/`debit`/`balance`/
`reverse_source`), nunca com as tabelas diretamente.

Append-only: nenhum lançamento é editado ou excluído — correções são feitas por **estorno**
(`reversed_at`). Qualquer outra instituição financeira poderá reutilizar este mesmo Ledger.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.advance_repasse_ledger import (
    AdvanceRepasseLedgerEntry,
    RepasseLedgerDirection,
    RepasseLedgerSource,
    RepasseWithdrawalPurpose,
)

_CENT = Decimal("0.01")


def _money(v: float | Decimal) -> Decimal:
    return Decimal(str(v)).quantize(_CENT)


@runtime_checkable
class RepasseLedgerPort(Protocol):
    """Interface mínima e estável que os consumidores (ex.: Liquidação) enxergam do Ledger.

    Recebe apenas dados primitivos — nenhum tipo "batch"/"lepta"/percentual. Isso garante que
    o consumidor jamais dependa das tabelas do Ledger nem de regras de instituição.
    """

    async def credit(
        self,
        *,
        institution_id: UUID,
        amount: float | Decimal,
        source_type: RepasseLedgerSource,
        occurred_at: date,
        description: str | None = ...,
        source_batch_id: UUID | None = ...,
        source_movement_id: UUID | None = ...,
        created_by_id: UUID | None = ...,
    ) -> AdvanceRepasseLedgerEntry: ...

    async def debit(
        self,
        *,
        institution_id: UUID,
        amount: float | Decimal,
        source_type: RepasseLedgerSource,
        occurred_at: date,
        description: str | None = ...,
        source_batch_id: UUID | None = ...,
        source_movement_id: UUID | None = ...,
        created_by_id: UUID | None = ...,
    ) -> AdvanceRepasseLedgerEntry: ...

    async def balance(self, institution_id: UUID) -> Decimal: ...

    async def reverse_source(
        self,
        *,
        source_movement_id: UUID | None = ...,
        source_batch_id: UUID | None = ...,
        reason: str | None = ...,
    ) -> int: ...


class AdvanceRepasseLedgerService:
    """Implementação concreta do `RepasseLedgerPort` sobre `advance_repasse_ledger`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- escrita (append-only) ------------------------------------------------

    async def _post(
        self,
        *,
        direction: RepasseLedgerDirection,
        institution_id: UUID,
        amount: float | Decimal,
        source_type: RepasseLedgerSource,
        occurred_at: date,
        description: str | None,
        source_batch_id: UUID | None,
        source_movement_id: UUID | None,
        created_by_id: UUID | None,
        withdrawal_purpose: RepasseWithdrawalPurpose | None = None,
    ) -> AdvanceRepasseLedgerEntry:
        val = _money(amount)
        if val <= 0:
            raise ValueError("O valor do lançamento do Ledger deve ser positivo.")
        entry = AdvanceRepasseLedgerEntry(
            institution_id=institution_id,
            direction=direction,
            amount=val,
            source_type=source_type,
            source_batch_id=source_batch_id,
            source_movement_id=source_movement_id,
            occurred_at=occurred_at,
            description=(description or None),
            withdrawal_purpose=withdrawal_purpose,
            created_by_id=created_by_id,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def credit(
        self,
        *,
        institution_id: UUID,
        amount: float | Decimal,
        source_type: RepasseLedgerSource,
        occurred_at: date,
        description: str | None = None,
        source_batch_id: UUID | None = None,
        source_movement_id: UUID | None = None,
        created_by_id: UUID | None = None,
    ) -> AdvanceRepasseLedgerEntry:
        return await self._post(
            direction=RepasseLedgerDirection.CREDIT,
            institution_id=institution_id,
            amount=amount,
            source_type=source_type,
            occurred_at=occurred_at,
            description=description,
            source_batch_id=source_batch_id,
            source_movement_id=source_movement_id,
            created_by_id=created_by_id,
        )

    async def debit(
        self,
        *,
        institution_id: UUID,
        amount: float | Decimal,
        source_type: RepasseLedgerSource,
        occurred_at: date,
        description: str | None = None,
        source_batch_id: UUID | None = None,
        source_movement_id: UUID | None = None,
        created_by_id: UUID | None = None,
    ) -> AdvanceRepasseLedgerEntry:
        return await self._post(
            direction=RepasseLedgerDirection.DEBIT,
            institution_id=institution_id,
            amount=amount,
            source_type=source_type,
            occurred_at=occurred_at,
            description=description,
            source_batch_id=source_batch_id,
            source_movement_id=source_movement_id,
            created_by_id=created_by_id,
        )

    async def withdraw(
        self,
        *,
        institution_id: UUID,
        amount: float | Decimal,
        purpose: RepasseWithdrawalPurpose,
        occurred_at: date,
        description: str | None = None,
        created_by_id: UUID | None = None,
    ) -> AdvanceRepasseLedgerEntry:
        """Registra uma **Retirada de Repasse** — DÉBITO que apenas reduz o saldo disponível.

        Não é liquidação de NF (por isso `source_type=WITHDRAWAL`). Fica com o destino ESTRUTURADO
        (`purpose`), não no texto. Guarda de saldo único: a retirada não pode exceder o
        `Saldo do Repasse = Entradas − Liquidações − Retiradas` = `balance()` (Σ CREDIT − Σ DEBIT
        dos ativos, já incluindo retiradas anteriores) — assim o Repasse nunca fica negativo.
        """
        val = _money(amount)
        if val <= 0:
            raise ValueError("O valor da retirada deve ser positivo.")
        saldo = await self.balance(institution_id)
        if val > saldo + _CENT:
            raise ValueError(
                f"Retirada excede o Saldo do Repasse. Disponível: {saldo:.2f}; solicitado: {val:.2f}."
            )
        return await self._post(
            direction=RepasseLedgerDirection.DEBIT,
            institution_id=institution_id,
            amount=val,
            source_type=RepasseLedgerSource.WITHDRAWAL,
            occurred_at=occurred_at,
            description=description,
            source_batch_id=None,
            source_movement_id=None,
            created_by_id=created_by_id,
            withdrawal_purpose=purpose,
        )

    # --- leitura --------------------------------------------------------------

    async def balance(self, institution_id: UUID) -> Decimal:
        """Saldo = Σ CREDIT − Σ DEBIT dos lançamentos ATIVOS (não estornados)."""
        rows = (
            await self.db.execute(
                select(AdvanceRepasseLedgerEntry.direction, AdvanceRepasseLedgerEntry.amount).where(
                    AdvanceRepasseLedgerEntry.institution_id == institution_id,
                    AdvanceRepasseLedgerEntry.reversed_at.is_(None),
                )
            )
        ).all()
        total = Decimal("0.00")
        for direction, amount in rows:
            if direction == RepasseLedgerDirection.CREDIT:
                total += _money(amount)
            else:
                total -= _money(amount)
        return total.quantize(_CENT)

    async def active_credit_total(self, *, source_batch_id: UUID) -> Decimal:
        """Σ dos CRÉDITOS ATIVOS de uma operação (usado para guardar a reversão da operação)."""
        rows = (
            await self.db.execute(
                select(AdvanceRepasseLedgerEntry.amount).where(
                    AdvanceRepasseLedgerEntry.source_batch_id == source_batch_id,
                    AdvanceRepasseLedgerEntry.direction == RepasseLedgerDirection.CREDIT,
                    AdvanceRepasseLedgerEntry.reversed_at.is_(None),
                )
            )
        ).all()
        return sum((_money(a) for (a,) in rows), Decimal("0.00")).quantize(_CENT)

    async def entries_for_batch(self, batch_id: UUID) -> list[AdvanceRepasseLedgerEntry]:
        """Lançamentos ligados a uma operação (para o histórico do borderô). Read-only."""
        stmt = (
            select(AdvanceRepasseLedgerEntry)
            .where(AdvanceRepasseLedgerEntry.source_batch_id == batch_id)
            .order_by(AdvanceRepasseLedgerEntry.occurred_at.asc(), AdvanceRepasseLedgerEntry.created_at.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def statement(
        self,
        *,
        institution_id: UUID | None = None,
        include_reversed: bool = True,
    ) -> list[AdvanceRepasseLedgerEntry]:
        """Extrato ordenado (mais antigo primeiro). Read-only."""
        stmt = select(AdvanceRepasseLedgerEntry)
        if institution_id is not None:
            stmt = stmt.where(AdvanceRepasseLedgerEntry.institution_id == institution_id)
        if not include_reversed:
            stmt = stmt.where(AdvanceRepasseLedgerEntry.reversed_at.is_(None))
        stmt = stmt.order_by(
            AdvanceRepasseLedgerEntry.occurred_at.asc(), AdvanceRepasseLedgerEntry.created_at.asc()
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # --- estorno (nunca update/delete) ---------------------------------------

    async def reverse_source(
        self,
        *,
        source_movement_id: UUID | None = None,
        source_batch_id: UUID | None = None,
        reason: str | None = None,
    ) -> int:
        """Estorna (soft) os lançamentos ATIVOS de uma origem. Retorna quantos foram estornados.

        Idempotente: lançamentos já estornados são ignorados. Não apaga nada.
        """
        if source_movement_id is None and source_batch_id is None:
            raise ValueError("Informe source_movement_id ou source_batch_id para estornar.")
        stmt = select(AdvanceRepasseLedgerEntry).where(AdvanceRepasseLedgerEntry.reversed_at.is_(None))
        if source_movement_id is not None:
            stmt = stmt.where(AdvanceRepasseLedgerEntry.source_movement_id == source_movement_id)
        if source_batch_id is not None:
            stmt = stmt.where(AdvanceRepasseLedgerEntry.source_batch_id == source_batch_id)
        entries = list((await self.db.execute(stmt)).scalars().all())
        now = datetime.now(timezone.utc)
        for e in entries:
            e.reversed_at = now
            e.reversal_reason = (reason or None)
        if entries:
            await self.db.flush()
        return len(entries)
